import io
import os
import sys
import contextlib
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
        self._broken = False

    def set_brightness(self, percent):
        with self._lock:
            try:
                self._deck.set_brightness(percent)
            except Exception as e:
                self._broken = True
                raise e

    def set_key_image(self, key, image):
        with self._lock:
            try:
                self._deck.set_key_image(key, image)
            except Exception as e:
                self._broken = True
                raise e

    def set_touchscreen_image(self, image, x_pos=0, y_pos=0, width=0, height=0):
        with self._lock:
            try:
                self._deck.set_touchscreen_image(image, x_pos, y_pos, width, height)
            except Exception as e:
                self._broken = True
                raise e

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
        return self._deck.is_open() and not self._broken

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
    default_cfg = {
        "pages": [
            {"keys": {}, "dials": {}}
        ],
        "active_page_index": 0,
        "global_styles": {
            "key_bg_color": "#0f172a",
            "key_font_family": "Outfit",
            "key_font_size": 12,
            "key_label_position": "top",
            "dial_bg_color": "#0f172a",
            "dial_font_family": "Outfit",
            "dial_font_size": 13,
            "dial_label_position": "left"
        }
    }
    if not CONFIG_PATH.exists():
        return default_cfg
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)
        
        # Migration: if "keys" and "dials" are at root level, migrate to "pages"
        if "keys" in cfg and "dials" in cfg and "pages" not in cfg:
            cfg = {
                "pages": [
                    {"keys": cfg.get("keys", {}), "dials": cfg.get("dials", {})}
                ],
                "active_page_index": 0,
                "global_styles": default_cfg["global_styles"]
            }
        
        # Ensure pages has at least one page
        if "pages" not in cfg or not isinstance(cfg["pages"], list) or len(cfg["pages"]) == 0:
            cfg["pages"] = [{"keys": {}, "dials": {}}]
            
        # Ensure active_page_index is valid
        if "active_page_index" not in cfg:
            cfg["active_page_index"] = 0
        elif cfg["active_page_index"] >= len(cfg["pages"]):
            cfg["active_page_index"] = 0
            
        # Ensure global_styles has values
        if "global_styles" not in cfg or not isinstance(cfg["global_styles"], dict):
            cfg["global_styles"] = default_cfg["global_styles"]
        else:
            for k, v in default_cfg["global_styles"].items():
                cfg["global_styles"].setdefault(k, v)
                
        return cfg
    except Exception as e:
        print(f"[DAEMON] Error reading config: {e}")
        return default_cfg

def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[DAEMON] Error saving config: {e}")

# ---------------------------------------------------------------------------
# Stream Deck Hardware Operations
# ---------------------------------------------------------------------------

drawing_lock = threading.Lock()

@contextlib.contextmanager
def apply_global_styles_context(global_styles):
    original_new = Image.new
    original_load_default = ImageFont.load_default
    original_text = ImageDraw.ImageDraw.text
    
    original_rectangle = ImageDraw.ImageDraw.rectangle
    
    def parse_hex(hex_str, default):
        try:
            hex_str = hex_str.lstrip('#')
            return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
        except:
            return default

    def patched_new(mode, size, color=0):
        if size == (120, 120):
            bg = global_styles.get("key_bg_color", "#0f172a")
            color = parse_hex(bg, (15, 23, 42))
        elif size == (200, 100) or size == (SEGMENT_WIDTH, SCREEN_HEIGHT):
            bg = global_styles.get("dial_bg_color", "#0f172a")
            color = parse_hex(bg, (20, 20, 20))
        return original_new(mode, size, color)

    def patched_load_default(size=None, **kwargs):
        font_family = global_styles.get("key_font_family", "Outfit")
        
        # Determine standard system fonts on Linux system (DejaVuSans or LiberationSans)
        font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        if font_family.lower() == "dejavu":
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        
        # Check size override and adjust proportionally
        if size is not None:
            style_size = global_styles.get("key_font_size", 12)
            if size <= 15:
                size = style_size
            else:
                size = int(size * (style_size / 12.0))
                
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size or 12)
            except:
                pass
        return original_load_default(size=size, **kwargs)

    def patched_text(self, xy, text, fill=None, font=None, *args, **kwargs):
        x, y = xy
        w, h = self.im.size
        
        if w == 120 and h == 120:
            # Key rendering coordinate adjustment
            pos = global_styles.get("key_label_position", "top")
            if pos == "bottom":
                if y < 25:
                    y = y + 78
                elif 25 <= y < 70:
                    y = y - 10
                elif y >= 70:
                    y = y - 45
            elif pos == "middle":
                if y < 25:
                    y = y + 33
                elif 25 <= y < 70:
                    y = y - 25
        elif w == 200 and h == 100:
            # Dial segment rendering coordinate adjustment
            pos = global_styles.get("dial_label_position", "left")
            if x == 15:
                if pos == "center":
                    if font:
                        try:
                            bbox = self.textbbox((0, 0), text, font=font)
                            tw = bbox[2] - bbox[0]
                            x = (w - tw) // 2
                        except:
                            pass
                elif pos == "right":
                    if font:
                        try:
                            bbox = self.textbbox((0, 0), text, font=font)
                            tw = bbox[2] - bbox[0]
                            x = w - tw - 15
                        except:
                            pass
                        
        xy = (x, y)
        return original_text(self, xy, text, fill, font, *args, **kwargs)

    def patched_rectangle(self, xy, fill=None, outline=None, width=1):
        w, h = self.im.size
        # Dial segment full background override
        if w == 200 and h == 100:
            if fill == (20, 20, 20) and len(xy) == 4 and xy[0] == 0 and xy[1] == 0 and xy[2] >= w - 1 and xy[3] >= h - 1:
                bg = global_styles.get("dial_bg_color", "#0f172a")
                fill = parse_hex(bg, (20, 20, 20))
        # Key full background override (if any plugin draws one)
        elif w == 120 and h == 120:
            if len(xy) == 4 and xy[0] == 0 and xy[1] == 0 and xy[2] >= w - 1 and xy[3] >= h - 1:
                bg = global_styles.get("key_bg_color", "#0f172a")
                fill = parse_hex(bg, (15, 23, 42))
        return original_rectangle(self, xy, fill, outline, width)

    # Apply patches
    Image.new = patched_new
    ImageFont.load_default = patched_load_default
    ImageDraw.ImageDraw.text = patched_text
    ImageDraw.ImageDraw.rectangle = patched_rectangle
    try:
        yield
    finally:
        # Restore original functions
        Image.new = original_new
        ImageFont.load_default = original_load_default
        ImageDraw.ImageDraw.text = original_text
        ImageDraw.ImageDraw.rectangle = original_rectangle


def update_lcd_strip():
    """Redraw the 4-segment LCD touchscreen strip and push it to hardware."""
    global deck
    if deck is None:
        return
        
    cfg = load_config()
    pages = cfg.get("pages", [])
    page_count = len(pages)
    active_page_idx = cfg.get("active_page_index", 0)
    global_styles = cfg.get("global_styles", {})
    
    with drawing_lock, apply_global_styles_context(global_styles):
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
        
    # Draw page indicator dots if multiple pages exist
    if page_count > 1:
        canvas_draw = ImageDraw.Draw(canvas)
        dot_radius = 3
        dot_spacing = 14
        total_w = (page_count - 1) * dot_spacing
        start_x = (SCREEN_WIDTH - total_w) // 2
        dot_y = SCREEN_HEIGHT - 8
        for p in range(page_count):
            cx = start_x + p * dot_spacing
            fill_color = (59, 130, 246) if p == active_page_idx else (75, 85, 99)
            canvas_draw.ellipse([cx - dot_radius, dot_y - dot_radius, cx + dot_radius, dot_y + dot_radius], fill=fill_color)
            
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
        
    cfg = load_config()
    global_styles = cfg.get("global_styles", {})
    
    if plugin:
        try:
            with drawing_lock, apply_global_styles_context(global_styles):
                img_bytes = plugin.get_image("IDLE")
        except Exception as e:
            print(f"[DAEMON] Error generating image for key {key_index}: {e}")
            img_bytes = None
    else:
        # Default empty image styled to match custom background with unassigned labels
        try:
            with drawing_lock, apply_global_styles_context(global_styles):
                img = Image.new("RGB", (120, 120))
                draw = ImageDraw.Draw(img)
                # Draw subtle outline border
                draw.rectangle([3, 3, 116, 116], outline=(55, 65, 81), width=1)
                
                try:
                    font_small = ImageFont.load_default(size=11)
                except Exception:
                    font_small = ImageFont.load_default()
                
                t1 = f"Key {key_index + 1}"
                t2 = "Unassigned"
                
                # Draw labels centered
                bbox1 = draw.textbbox((0, 0), t1, font=font_small)
                tw1 = bbox1[2] - bbox1[0]
                draw.text(((120 - tw1) // 2, 45), t1, fill=(100, 116, 139), font=font_small)
                
                bbox2 = draw.textbbox((0, 0), t2, font=font_small)
                tw2 = bbox2[2] - bbox2[0]
                draw.text(((120 - tw2) // 2, 62), t2, fill=(71, 85, 105), font=font_small)
                
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=95)
                img_bytes = buf.getvalue()
        except Exception as e:
            print(f"[DAEMON] Error generating blank key image: {e}")
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
    
    # Get active page config
    active_idx = cfg.get("active_page_index", 0)
    pages = cfg.get("pages", [])
    if active_idx >= len(pages):
        active_idx = 0
    active_page = pages[active_idx]
    
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
        for key_str, item in active_page.get("keys", {}).items():
            k_idx = int(key_str)
            p_name = item.get("plugin")
            settings = item.get("settings", {})
            if p_name in available_plugins:
                try:
                    plugin_inst = available_plugins[p_name](settings)
                    plugin_inst.redraw_callback = lambda idx=k_idx: update_key_display(idx)
                    new_keys[k_idx] = plugin_inst
                except Exception as e:
                    print(f"[DAEMON] Failed to instantiate key plugin {p_name}: {e}")
                    
        # Bind new dials
        for dial_str, item in active_page.get("dials", {}).items():
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
    global deck
    if deck is None:
        return
    with state_lock:
        plugin = key_plugins.get(key)
        
    cfg = load_config()
    global_styles = cfg.get("global_styles", {})
    
    if plugin:
        try:
            if pressed:
                if hasattr(plugin, "on_press"):
                    plugin.on_press()
                # Update button visuals immediately to PRESSED state
                with drawing_lock, apply_global_styles_context(global_styles):
                    img_bytes = plugin.get_image("PRESSED")
                deck.set_key_image(key, img_bytes)
            else:
                if hasattr(plugin, "on_release"):
                    plugin.on_release()
                # Fall back to normal state
                with drawing_lock, apply_global_styles_context(global_styles):
                    img_bytes = plugin.get_image("RELEASED")
                deck.set_key_image(key, img_bytes)
                # Let it settle back to IDLE
                def restore():
                    time.sleep(0.4)
                    update_key_display(key)
                threading.Thread(target=restore, daemon=True).start()
        except Exception as e:
            print(f"[DAEMON] Key callback error on {key}: {e}")


def deck_dial_callback(deck_device, dial, pressed, rotation):
    global last_click_time, deck
    if deck is None:
        return
    with state_lock:
        plugin = dial_plugins.get(dial)
        
    if not plugin:
        return
        
    try:
        if rotation != 0:
            plugin.on_rotate(rotation, deck)
            update_lcd_strip()
        else:
            now = time.time()
            if (now - last_click_time.get(dial, 0)) > DEBOUNCE_COOLDOWN:
                plugin.on_click(pressed, deck)
                last_click_time[dial] = now
                update_lcd_strip()
    except Exception as e:
        print(f"[DAEMON] Dial callback error on {dial}: {e}")


last_page_switch_time = 0.0

def deck_touchscreen_callback(deck_device, event_type, value):
    global last_click_time, last_page_switch_time, deck
    if deck is None:
        return
    
    # Intercept drag event for horizontal swipe page switching
    evt_name = getattr(event_type, "name", "")
    if event_type == 3 or event_type == "DRAG" or evt_name == "DRAG":
        now = time.time()
        if now - last_page_switch_time > 0.8:
            x_start = value.get("x", 0)
            x_end = value.get("x_out", 0)
            dx = x_end - x_start
            
            if abs(dx) > 150:
                last_page_switch_time = now
                cfg = load_config()
                pages = cfg.get("pages", [])
                active_idx = cfg.get("active_page_index", 0)
                
                if dx < 0:
                    # Swipe left -> Next Page
                    new_idx = (active_idx + 1) % len(pages)
                else:
                    # Swipe right -> Previous Page
                    new_idx = (active_idx - 1) % len(pages)
                    
                if new_idx != active_idx:
                    print(f"[DAEMON] Page swipe gesture: page {active_idx + 1} -> {new_idx + 1}")
                    cfg["active_page_index"] = new_idx
                    save_config(cfg)
                    apply_assignments(cfg)
                return
        return

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
            plugin.on_touch(event_type, value, deck)
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
    cfg = load_config()
    res = {
        "status": "Disconnected",
        "device": None,
        "active_page_index": cfg.get("active_page_index", 0)
    }
    if deck is None:
        return res
    try:
        res.update({
            "status": "Connected",
            "device": deck.deck_type(),
            "serial": deck.get_serial_number(),
            "firmware": deck.get_firmware_version()
        })
        return res
    except Exception as e:
        res.update({"status": "Connected", "device": "Stream Deck", "error": str(e)})
        return res


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
    active_idx = cfg.get("active_page_index", 0)
    pages = cfg.get("pages", [])
    if active_idx >= len(pages):
        active_idx = 0
    active_page = pages[active_idx]
    
    target_section = "keys" if assignment.type == "key" else "dials"
    
    # Store settings
    active_page[target_section][str(assignment.index)] = {
        "plugin": assignment.plugin,
        "settings": assignment.settings
    }
    
    save_config(cfg)
    apply_assignments(cfg)
    return {"message": "Success", "config": cfg}


@app.post("/api/remove")
def remove_plugin_endpoint(target: RemoveModel):
    cfg = load_config()
    active_idx = cfg.get("active_page_index", 0)
    pages = cfg.get("pages", [])
    if active_idx >= len(pages):
        active_idx = 0
    active_page = pages[active_idx]
    
    target_section = "keys" if target.type == "key" else "dials"
    
    idx_str = str(target.index)
    if idx_str in active_page[target_section]:
        del active_page[target_section][idx_str]
        
    save_config(cfg)
    apply_assignments(cfg)
    return {"message": "Success", "config": cfg}


class PageSwitchModel(BaseModel):
    index: int


class PageDeleteModel(BaseModel):
    index: int


@app.post("/api/pages/switch")
def switch_page(data: PageSwitchModel):
    cfg = load_config()
    pages = cfg.get("pages", [])
    if 0 <= data.index < len(pages):
        cfg["active_page_index"] = data.index
        save_config(cfg)
        apply_assignments(cfg)
        return {"message": "Success", "config": cfg}
    raise HTTPException(status_code=400, detail="Invalid page index")


@app.post("/api/pages/add")
def add_page():
    cfg = load_config()
    cfg.setdefault("pages", []).append({"keys": {}, "dials": {}})
    cfg["active_page_index"] = len(cfg["pages"]) - 1
    save_config(cfg)
    apply_assignments(cfg)
    return {"message": "Success", "config": cfg}


@app.post("/api/pages/delete")
def delete_page(data: PageDeleteModel):
    cfg = load_config()
    pages = cfg.get("pages", [])
    if len(pages) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the only page")
    if 0 <= data.index < len(pages):
        pages.pop(data.index)
        active_idx = cfg.get("active_page_index", 0)
        if active_idx >= len(pages):
            cfg["active_page_index"] = len(pages) - 1
        elif active_idx > data.index:
            cfg["active_page_index"] = active_idx - 1
        save_config(cfg)
        apply_assignments(cfg)
        return {"message": "Success", "config": cfg}
    raise HTTPException(status_code=400, detail="Invalid page index")


class StylesModel(BaseModel):
    key_bg_color: str
    key_font_family: str
    key_font_size: int
    key_label_position: str
    dial_bg_color: str
    dial_font_family: str
    dial_font_size: int
    dial_label_position: str


@app.post("/api/styles")
def save_styles(styles: StylesModel):
    cfg = load_config()
    cfg["global_styles"] = styles.dict()
    save_config(cfg)
    # We do not strictly need to rebuild running plugins but this persists it
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
