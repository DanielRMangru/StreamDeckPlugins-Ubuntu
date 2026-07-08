import time
import subprocess
import threading
from PIL import ImageDraw, ImageFont
from plugin_base import DialPlugin

_ALERT_SOUND_FILE = "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"
_ALERT_SOUNDS = [
    ("pw-play",      [_ALERT_SOUND_FILE]),
    ("gst-play-1.0", [_ALERT_SOUND_FILE]),
    ("ffplay",       ["-nodisp", "-autoexit", _ALERT_SOUND_FILE]),
]

def play_alert_sound():
    print("[SOUND] Attempting alert sound...")
    for cmd, args in _ALERT_SOUNDS:
        try:
            result = subprocess.run(
                [cmd] + args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True
            )
            if result.returncode == 0:
                print(f"[SOUND] Played via {cmd}")
                return
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"[SOUND] {cmd} error: {e}")
    # Fallback to terminal bell
    sys.stdout.write("\a")
    sys.stdout.flush()

class TimerPlugin(DialPlugin):
    name = "Countdown Timer"
    description = "Set duration by rotating, push/tap to start/stop, hold dial to reset. Plays sound when done."
    author = "System"
    version = "1.0.0"
    
    def __init__(self, settings: dict = None):
        super().__init__(settings)
        self.seconds = 0
        self.total_seconds = 0
        self.state = "IDLE"  # IDLE, SET, RUNNING, PAUSED, DONE
        self.lock = threading.Lock()
        self.thread = None
        self.redraw_callback = None
        self.press_time = 0.0
        
    def cleanup(self):
        with self.lock:
            self.state = "IDLE"  # Stops thread loop
            
    def draw_segment(self, draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
        draw.rectangle([0, 0, width, height], fill=(20, 20, 20))
        
        try:
            font_title = ImageFont.load_default(size=13)
            font_val = ImageFont.load_default(size=19)
            font_small = ImageFont.load_default(size=11)
        except Exception:
            font_title = font_val = font_small = ImageFont.load_default()
            
        draw.text((15, 8), "TIMER", fill=(150, 150, 150), font=font_title)
        
        with self.lock:
            secs = self.seconds
            total = self.total_seconds
            state = self.state
            
        badge_map = {
            "IDLE":    ("IDLE",  (80,  80,  80)),
            "SET":     ("SET",   (80, 140, 255)),
            "RUNNING": ("RUNNING", (255, 140, 0)),
            "PAUSED":  ("PAUSED",  (200, 160, 0)),
            "DONE":    ("✓DONE", (255,  60,  60)),
        }
        badge_text, badge_color = badge_map.get(state, ("?", (80, 80, 80)))
        draw.text((width - 65, 8), badge_text, fill=badge_color, font=font_title)
        
        # Format time
        h = secs // 3600
        m = (secs % 3600) // 60
        s = secs % 60
        time_str = f"{h:02d}:{m:02d}:{s:02d}"
        
        bbox = draw.textbbox((0, 0), time_str, font=font_val)
        tw = bbox[2] - bbox[0]
        tx = (width - tw) // 2
        
        t_color = (255, 60, 60) if state == "DONE" else (255, 255, 255) if state in ("RUNNING", "PAUSED") else (140, 140, 140)
        draw.text((tx, 30), time_str, fill=t_color, font=font_val)
        
        # Progress bar
        pct = (secs / total) if total > 0 and state in ("RUNNING", "PAUSED", "DONE") else 1.0 if state == "SET" else 0.0
        bar_color = (255, 60, 60) if state == "DONE" else (255, 140, 0)
        
        draw.rectangle([15, 67, 185, 77], fill=(40, 40, 40))
        fill_w = int(170 * pct)
        if fill_w > 0:
            draw.rectangle([15, 67, 15 + fill_w, 77], fill=bar_color)
            
        if state in ("RUNNING", "PAUSED", "SET"):
            draw.text((15, height - 16), "hold=reset", fill=(55, 55, 55), font=font_small)
        else:
            draw.text((width - 52, height - 16), "[ tap ]", fill=(55, 55, 55), font=font_small)
            
    def on_rotate(self, ticks: int, deck):
        with self.lock:
            if self.state == "RUNNING":
                return
            self.seconds = max(0, min(5999 * 60, self.seconds + ticks * 30))
            if self.seconds > 0:
                self.state = "SET"
                self.total_seconds = self.seconds
            else:
                self.state = "IDLE"
                self.total_seconds = 0
                
        if self.redraw_callback:
            self.redraw_callback()
            
    def on_click(self, pressed: bool, deck):
        if pressed:
            self.press_time = time.time()
        else:
            held = time.time() - self.press_time
            if held >= 0.8:
                self.reset()
            else:
                self.toggle_start_stop()
                
    def on_touch(self, event_type, value: dict, deck):
        if event_type == 1 or event_type == "SHORT" or getattr(event_type, "name", "") == "SHORT":
            self.toggle_start_stop()
            
    def toggle_start_stop(self):
        with self.lock:
            if self.state == "IDLE":
                return
            if self.state in ("SET", "PAUSED"):
                if self.seconds <= 0:
                    return
                self.state = "RUNNING"
                t = threading.Thread(target=self._countdown_thread, daemon=True)
                self.thread = t
                t.start()
            elif self.state == "RUNNING":
                self.state = "PAUSED"
            elif self.state == "DONE":
                self.reset()
                return
                
        if self.redraw_callback:
            self.redraw_callback()
            
    def reset(self):
        with self.lock:
            self.state = "IDLE"
            self.seconds = 0
            self.total_seconds = 0
        if self.redraw_callback:
            self.redraw_callback()
            
    def _countdown_thread(self):
        while True:
            time.sleep(1)
            with self.lock:
                if self.state != "RUNNING":
                    break
                self.seconds -= 1
                if self.seconds <= 0:
                    self.seconds = 0
                    self.state = "DONE"
                    # Spawn sound thread (non-daemon to avoid premature termination)
                    threading.Thread(target=play_alert_sound, daemon=False).start()
                    
            if self.redraw_callback:
                self.redraw_callback()
                
            with self.lock:
                if self.state in ("DONE", "PAUSED", "IDLE"):
                    break
