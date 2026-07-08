import io
import time
import glob
import threading
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from plugin_base import BasePlugin

class CpuTempPlugin(BasePlugin):
    name = "CPU Temp"
    description = "Displays live overall CPU temperature."
    author = "System"
    version = "1.0.0"
    target = "both"
    
    def __init__(self, settings: dict = None):
        super().__init__(settings)
        self.temp = 0.0
        self.running = True
        self.redraw_callback = None
        self.sensor_path = self._discover_sensor()
        
        if self.sensor_path:
            print(f"[CPU TEMP] Found sensor path: {self.sensor_path}")
        else:
            print("[CPU TEMP] Warning: no matching hwmon sensor path found, falling back to thermal_zone0")
            
        # Start background polling thread
        self.thread = threading.Thread(target=self._poll_temp, daemon=True)
        self.thread.start()
        
    def cleanup(self):
        self.running = False
        
    def _discover_sensor(self):
        # Match k10temp (AMD), coretemp (Intel), zenpower
        targets = ["k10temp", "coretemp", "zenpower"]
        for path in glob.glob("/sys/class/hwmon/hwmon*"):
            try:
                name_file = Path(path) / "name"
                if name_file.exists():
                    with open(name_file, "r") as f:
                        name = f.read().strip()
                    if any(t in name for t in targets):
                        # Ensure a temp1_input exists
                        if (Path(path) / "temp1_input").exists():
                            return Path(path) / "temp1_input"
                        # Or search for any temp*_input
                        inputs = list(Path(path).glob("temp*_input"))
                        if inputs:
                            return inputs[0]
            except:
                pass
        
        # Fallback to general thermal zone
        fallback = Path("/sys/class/thermal/thermal_zone0/temp")
        if fallback.exists():
            return fallback
        return None
        
    def _read_temp(self):
        if not self.sensor_path:
            return 0.0
        try:
            with open(self.sensor_path, "r") as f:
                val = float(f.read().strip())
            # Milli-degrees Celsius or raw Celsius
            if val > 1000.0:
                return val / 1000.0
            return val
        except:
            return 0.0
            
    def _poll_temp(self):
        while self.running:
            self.temp = self._read_temp()
            if self.redraw_callback:
                self.redraw_callback()
            time.sleep(1.5)
            
    def get_image(self, state: str) -> bytes:
        img = Image.new("RGB", (120, 120), color=(17, 24, 39))
        draw = ImageDraw.Draw(img)
        draw.rectangle([3, 3, 116, 116], outline=(31, 41, 55), width=2)
        
        try:
            font_title = ImageFont.load_default(size=11)
            font_val = ImageFont.load_default(size=26)
            font_lbl = ImageFont.load_default(size=11)
        except Exception:
            font_title = font_val = font_lbl = ImageFont.load_default()
            
        bbox = draw.textbbox((0, 0), "CPU TEMP", font=font_title)
        draw.text(((120 - (bbox[2] - bbox[0])) // 2, 18), "CPU TEMP", fill=(239, 68, 68), font=font_title)
        
        val_str = f"{int(self.temp)}°C"
        bbox = draw.textbbox((0, 0), val_str, font=font_val)
        draw.text(((120 - (bbox[2] - bbox[0])) // 2, 45), val_str, fill=(255, 255, 255), font=font_val)
        
        # Draw temperature scale bar (0-100°C)
        draw.rectangle([15, 95, 105, 101], fill=(55, 65, 81))
        fill_w = int(90 * (max(0, min(100, self.temp)) / 100.0))
        if fill_w > 0:
            # Color gradient: blue to red
            color = (59, 130, 246) if self.temp < 50 else (245, 158, 11) if self.temp < 75 else (239, 68, 68)
            draw.rectangle([15, 95, 15 + fill_w, 101], fill=color)
            
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()
        
    def draw_segment(self, draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
        draw.rectangle([0, 0, width, height], fill=(20, 20, 20))
        
        try:
            font_title = ImageFont.load_default(size=13)
            font_val = ImageFont.load_default(size=15)
        except Exception:
            font_title = font_val = ImageFont.load_default()
            
        draw.text((15, 10), "CPU TEMP", fill=(150, 150, 150), font=font_title)
        
        val_str = f"{self.temp:.1f}°C"
        draw.text((15, 30), val_str, fill=(255, 255, 255), font=font_val)
        
        # Progress bar
        draw.rectangle([15, 65, 185, 77], fill=(40, 40, 40))
        fill_w = int(170 * (max(0, min(100, self.temp)) / 100.0))
        if fill_w > 0:
            color = (59, 130, 246) if self.temp < 50 else (245, 158, 11) if self.temp < 75 else (239, 68, 68)
            draw.rectangle([15, 65, 15 + fill_w, 77], fill=color)
