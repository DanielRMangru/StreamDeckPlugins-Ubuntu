import io
import os
import sys
import json
import time
import signal
import inspect
import importlib
import threading
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, Any, Optional

from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.Devices.StreamDeck import TouchscreenEventType

# Import base plugins
from plugin_base import BasePlugin, KeyPlugin, DialPlugin

# ---------------------------------------------------------------------------
# App state & configuration paths
# ---------------------------------------------------------------------------

CONFIG_PATH = Path(__file__).parent / "plugins_config.json"
WEB_DIR = Path(__file__).parent / "web"
WEB_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Stream Deck+ Config App")

# Shared variables
deck = None
running = True
state_lock = threading.Lock()
key_plugins: Dict[int, KeyPlugin] = {}
dial_plugins: Dict[int, DialPlugin] = {}
available_plugins: Dict[str, type] = {}

# ---------------------------------------------------------------------------
# Thread-safe Stream Deck Wrapper
# ---------------------------------------------------------------------------

usb_write_lock = threading.Lock()

class ThreadSafeDeck:
    """
    Wraps the raw StreamDeck device and synchronizes all hardware operations
    using a global lock. This prevents concurrent read/writes from freezing
    the USB endpoint and locking/freezing the hardware.
    """
    def __init__(self, raw_deck, lock):
        self._deck = raw_deck
        self._lock = lock

    def set_brightness(self, percent):
        with self._lock:
            self._deck.set_brightness(percent)

    def set_key_image(self, key, image):
        with self._lock:
            self._deck.set_key_image(key, image)

    def set_touchscreen_image(self, image, x_pos=0, y_pos=0, width=0, height=0):
        with self._lock:
            self._deck.set_touchscreen_image(image, x_pos, y_pos, width, height)

    def reset(self):
        with self._lock:
            try:
                self._deck.reset()
            except Exception:
                pass

    def close(self):
        with self._lock:
            try:
                self._deck.close()
            except Exception:
                pass

    def is_open(self):
        return self._deck.is_open()

    def deck_type(self):
        return self._deck.deck_type()

    def get_serial_number(self):
        return self._deck.get_serial_number()

    def get_firmware_version(self):
        return self._deck.get_firmware_version()

    def set_key_callback(self, callback):
        self._deck.set_key_callback(callback)

    def set_dial_callback(self, callback):
        self._deck.set_dial_callback(callback)

    def set_touchscreen_callback(self, callback):
        self._deck.set_touchscreen_callback(callback)

# Constants for Stream Deck LCD strip
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 100
SEGMENT_WIDTH = 200

# Cache for last pressed times for debouncing
last_click_time = {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0}
DEBOUNCE_COOLDOWN = 0.3

# Default blank images
BLANK_KEY_IMAGE = Image.new("RGB", (120, 120), color=(10, 10, 10))

# ---------------------------------------------------------------------------
# Dynamic Plugin Loader
# ---------------------------------------------------------------------------

def discover_all_plugins():
    global available_plugins
    discovered = {}
    plugins_dir = Path(__file__).parent / "plugins"
    plugins_dir.mkdir(exist_ok=True)
    
    # Add plugins directory to sys.path to resolve imports cleanly
    sys_path_str = str(plugins_dir.resolve())
    if sys_path_str not in sys.path:
        sys.path.insert(0, sys_path_str)
        
    for path in plugins_dir.glob("*.py"):
        if path.name.startswith("_"):
            continue
        try:
            module_name = path.stem
            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
            else:
                module = importlib.import_module(module_name)
                
            for name, cls in inspect.getmembers(module, inspect.isclass):
                if (issubclass(cls, BasePlugin) and cls is not BasePlugin 
                        and cls is not KeyPlugin and cls is not DialPlugin):
                    discovered[cls.__name__] = cls
                    print(f"[DAEMON] Discovered plugin: {cls.__name__} ({cls.name})")
        except Exception as e:
            print(f"[DAEMON] Error loading plugin file {path}: {e}")
            
    with state_lock:
        available_plugins = discovered
    return discovered

# ---------------------------------------------------------------------------
# Active Config Loader/Saver
# ---------------------------------------------------------------------------

def load_config():
    if not CONFIG_PATH.exists():
        return {"keys": {}, "dials": {}}
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[DAEMON] Error reading config: {e}")
        return {"keys": {}, "dials": {}}

def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[DAEMON] Error saving config: {e}")

# ---------------------------------------------------------------------------
# Stream Deck Hardware Operations
# ---------------------------------------------------------------------------

def update_lcd_strip():
    """Redraw the 4-segment LCD touchscreen strip and push it to hardware."""
    global deck
    if deck is None:
        return
        
    canvas = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), color=(15, 15, 15))
    
    for i in range(4):
        segment = Image.new("RGB", (SEGMENT_WIDTH, SCREEN_HEIGHT), color=(20, 20, 20))
        draw = ImageDraw.Draw(segment)
        
        with state_lock:
            plugin = dial_plugins.get(i)
            
        if plugin:
            try:
                plugin.draw_segment(draw, SEGMENT_WIDTH, SCREEN_HEIGHT)
            except Exception as e:
                print(f"[DAEMON] Draw error on dial {i} ({plugin.name}): {e}")
                draw.text((15, 15), "Error drawing", fill=(255, 100, 100))
        else:
            # Draw empty segment placeholder
            try:
                font_small = ImageFont.load_default(size=12)
            except Exception:
                font_small = ImageFont.load_default()
            draw.text((15, 40), f"Dial {i+1} Unassigned", fill=(75, 85, 99), font=font_small)
            
        # Draw vertical separator lines
        draw.line([SEGMENT_WIDTH - 1, 0, SEGMENT_WIDTH - 1, SCREEN_HEIGHT], fill=(40, 40, 40))
        canvas.paste(segment, (i * SEGMENT_WIDTH, 0))
        
    # Convert and push
    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=95)
    jpeg_bytes = buf.getvalue()
    try:
        deck.set_touchscreen_image(jpeg_bytes, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)
    except Exception as e:
        print(f"[DAEMON] Failed to write touchscreen image: {e}")


def update_key_display(key_index):
    """Redraw specific LCD key image."""
    global deck
    if deck is None:
        return
        
    with state_lock:
        plugin = key_plugins.get(key_index)
        
    if plugin:
        try:
            img_bytes = plugin.get_image("IDLE")
        except Exception as e:
            print(f"[DAEMON] Error generating image for key {key_index}: {e}")
            img_bytes = None
    else:
        # Default empty image
        buf = io.BytesIO()
        BLANK_KEY_IMAGE.save(buf, format="JPEG", quality=95)
        img_bytes = buf.getvalue()
        
    if img_bytes:
        try:
            deck.set_key_image(key_index, img_bytes)
        except Exception as e:
            print(f"[DAEMON] Error updating key {key_index}: {e}")


def full_redraw():
    update_lcd_strip()
    for i in range(8):
        update_key_display(i)


def apply_assignments(cfg):
    """Apply the active JSON configuration to current runtime plugin instances."""
    global key_plugins, dial_plugins, deck
    
    # Reload plugins directory
    discover_all_plugins()
    
    new_keys = {}
    new_dials = {}
    
    with state_lock:
        # Cleanup old key plugins
        for k, p in key_plugins.items():
            try: p.cleanup()
            except Exception: pass
            
        # Cleanup old dial plugins
        for d, p in dial_plugins.items():
            try: p.cleanup()
            except Exception: pass
            
        # Bind new keys
        for key_str, item in cfg.get("keys", {}).items():
            k_idx = int(key_str)
            p_name = item.get("plugin")
            settings = item.get("settings", {})
            if p_name in available_plugins:
                try:
                    new_keys[k_idx] = available_plugins[p_name](settings)
                except Exception as e:
                    print(f"[DAEMON] Failed to instantiate key plugin {p_name}: {e}")
                    
        # Bind new dials
        for dial_str, item in cfg.get("dials", {}).items():
            d_idx = int(dial_str)
            p_name = item.get("plugin")
            settings = item.get("settings", {})
            if p_name in available_plugins:
                try:
                    plugin_inst = available_plugins[p_name](settings)
                    # Wire up redraw callback for the timer or dynamic dials
                    plugin_inst.redraw_callback = update_lcd_strip
                    new_dials[d_idx] = plugin_inst
                except Exception as e:
                    print(f"[DAEMON] Failed to instantiate dial plugin {p_name}: {e}")
                    
        key_plugins = new_keys
        dial_plugins = new_dials
        
    full_redraw()

# ---------------------------------------------------------------------------
# Hardware Callbacks
# ---------------------------------------------------------------------------

def deck_key_callback(deck_device, key, pressed):
    with state_lock:
        plugin = key_plugins.get(key)
        
    if plugin:
        try:
            if pressed:
                plugin.on_press()
                # Update button visuals immediately to PRESSED state
                img_bytes = plugin.get_image("PRESSED")
                deck_device.set_key_image(key, img_bytes)
            else:
                plugin.on_release()
                # Fall back to normal state
                img_bytes = plugin.get_image("RELEASED")
                deck_device.set_key_image(key, img_bytes)
                # Let it settle back to IDLE
                def restore():
                    time.sleep(0.4)
                    update_key_display(key)
                threading.Thread(target=restore, daemon=True).start()
        except Exception as e:
            print(f"[DAEMON] Key callback error on {key}: {e}")


def deck_dial_callback(deck_device, dial, pressed, rotation):
    global last_click_time
    with state_lock:
        plugin = dial_plugins.get(dial)
        
    if not plugin:
        return
        
    try:
        if rotation != 0:
            plugin.on_rotate(rotation, deck_device)
            update_lcd_strip()
        else:
            now = time.time()
            if (now - last_click_time.get(dial, 0)) > DEBOUNCE_COOLDOWN:
                plugin.on_click(pressed, deck_device)
                last_click_time[dial] = now
                update_lcd_strip()
    except Exception as e:
        print(f"[DAEMON] Dial callback error on {dial}: {e}")


def deck_touchscreen_callback(deck_device, event_type, value):
    global last_click_time
    # We map x coordinates (0-800) to corresponding dial zone (0-3)
    x = value.get("x", 0)
    dial = x // SEGMENT_WIDTH
    
    with state_lock:
        plugin = dial_plugins.get(dial)
        
    if not plugin:
        return
        
    try:
        now = time.time()
        if (now - last_click_time.get(dial, 0)) > DEBOUNCE_COOLDOWN:
            plugin.on_touch(event_type, value, deck_device)
            last_click_time[dial] = now
            update_lcd_strip()
    except Exception as e:
        print(f"[DAEMON] Touch callback error on zone {dial}: {e}")

# ---------------------------------------------------------------------------
# Stream Deck Connection Manager
# ---------------------------------------------------------------------------

def run_streamdeck_daemon():
    global deck, running
    print("[DAEMON] Starting Stream Deck loop...")
    
    while running:
        try:
            decks = DeviceManager().enumerate()
            if not decks:
                time.sleep(2)
                continue
                
            raw_deck = decks[0]
            raw_deck.open()
            deck = ThreadSafeDeck(raw_deck, usb_write_lock)
            deck.reset()
            
            # Safe setup
            try: deck.set_brightness(50)
            except: pass
            
            # Setup callbacks
            deck.set_key_callback(deck_key_callback)
            deck.set_dial_callback(deck_dial_callback)
            deck.set_touchscreen_callback(deck_touchscreen_callback)
            
            print(f"[DAEMON] Connected to {deck.deck_type()} - S/N: {deck.get_serial_number()}")
            
            # Initial assignment mapping
            cfg = load_config()
            apply_assignments(cfg)
            
            # Keep alive
            while running and deck.is_open():
                time.sleep(1)
                
        except Exception as e:
            print(f"[DAEMON] Connection lost or error occurred: {e}")
            if deck:
                try: deck.close()
                except: pass
                deck = None
            time.sleep(2)
            
    # Cleanup on close
    if deck:
        try:
            deck.set_dial_callback(None)
            deck.set_touchscreen_callback(None)
            deck.reset()
            deck.close()
        except:
            pass
        print("[DAEMON] Hardware cleanly closed.")

# ---------------------------------------------------------------------------
# API Data Models
# ---------------------------------------------------------------------------

class AssignmentModel(BaseModel):
    type: str       # "key" or "dial"
    index: int      # 0-7 for key, 0-3 for dial
    plugin: str     # Plugin class name (e.g. "ClockPlugin")
    settings: dict = {}

class RemoveModel(BaseModel):
    type: str
    index: int

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/status")
def get_status():
    global deck
    if deck is None:
        return {"status": "Disconnected", "device": None}
    try:
        return {
            "status": "Connected",
            "device": deck.deck_type(),
            "serial": deck.get_serial_number(),
            "firmware": deck.get_firmware_version()
        }
    except Exception as e:
        return {"status": "Connected", "device": "Stream Deck", "error": str(e)}


@app.get("/api/plugins")
def get_plugins():
    # Refresh plugins directory to detect new files
    discover_all_plugins()
    
    result = []
    with state_lock:
        for name, cls in available_plugins.items():
            result.append({
                "class_name": name,
                "name": cls.name,
                "description": cls.description,
                "author": cls.author,
                "version": cls.version,
                "target": cls.target,
                "settings_schema": getattr(cls, "settings_schema", [])
            })
    return result


@app.get("/api/config")
def get_config():
    return load_config()


@app.post("/api/assign")
def assign_plugin_endpoint(assignment: AssignmentModel):
    cfg = load_config()
    target_section = "keys" if assignment.type == "key" else "dials"
    
    # Store settings
    cfg[target_section][str(assignment.index)] = {
        "plugin": assignment.plugin,
        "settings": assignment.settings
    }
    
    save_config(cfg)
    apply_assignments(cfg)
    return {"message": "Success", "config": cfg}


@app.post("/api/remove")
def remove_plugin_endpoint(target: RemoveModel):
    cfg = load_config()
    target_section = "keys" if target.type == "key" else "dials"
    
    idx_str = str(target.index)
    if idx_str in cfg[target_section]:
        del cfg[target_section][idx_str]
        
    save_config(cfg)
    apply_assignments(cfg)
    return {"message": "Success", "config": cfg}

# ---------------------------------------------------------------------------
# App initialization & entrypoint
# ---------------------------------------------------------------------------

# Mount Web Directory
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")

def main():
    global running
    
    # Run Stream Deck loop in background
    daemon_thread = threading.Thread(target=run_streamdeck_daemon, daemon=True)
    daemon_thread.start()
    
    # Launch uvicorn on port 8000
    import uvicorn
    try:
        uvicorn.run(app, host="127.0.0.1", port=8000)
    except KeyboardInterrupt:
        pass
    finally:
        running = False
        print("[SERVER] Shutting down...")

if __name__ == "__main__":
    main()
