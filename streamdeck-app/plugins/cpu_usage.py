import io
import time
import threading
from PIL import Image, ImageDraw, ImageFont
from plugin_base import BasePlugin

class CpuUsagePlugin(BasePlugin):
    name = "CPU Usage"
    description = "Displays live overall CPU utilization percentage."
    author = "System"
    version = "1.0.0"
    target = "both"  # Supports both button keys and dial screen segments
    
    def __init__(self, settings: dict = None):
        super().__init__(settings)
        self.usage = 0.0
        self.last_total = 0.0
        self.last_idle = 0.0
        self.running = True
        self.redraw_callback = None
        
        # Read initial values
        self.last_total, self.last_idle = self._read_cpu_times()
        
        # Start background polling thread
        self.thread = threading.Thread(target=self._poll_cpu, daemon=True)
        self.thread.start()
        
    def cleanup(self):
        self.running = False
        
    def _read_cpu_times(self):
        try:
            with open("/proc/stat", "r") as f:
                first_line = f.readline()
            if first_line.startswith("cpu "):
                fields = [float(val) for val in first_line.strip().split()[1:]]
                idle = fields[3] + fields[4]  # idle + iowait
                total = sum(fields[:8])        # user, nice, system, idle, iowait, irq, softirq, steal
                return total, idle
        except Exception as e:
            print(f"[CPU] Error reading /proc/stat: {e}")
        return 0.0, 0.0
        
    def _poll_cpu(self):
        while self.running:
            time.sleep(1.0)
            total, idle = self._read_cpu_times()
            if total > self.last_total:
                diff_total = total - self.last_total
                diff_idle = idle - self.last_idle
                self.usage = max(0.0, min(100.0, (1.0 - (diff_idle / diff_total)) * 100.0))
            self.last_total = total
            self.last_idle = idle
            
            # Request redraw
            if self.redraw_callback:
                self.redraw_callback()
                
    def get_image(self, state: str) -> bytes:
        # Button display: Dark background with green/blue accents
        img = Image.new("RGB", (120, 120), color=(17, 24, 39))
        draw = ImageDraw.Draw(img)
        draw.rectangle([3, 3, 116, 116], outline=(31, 41, 55), width=2)
        
        try:
            font_title = ImageFont.load_default(size=11)
            font_val = ImageFont.load_default(size=26)
            font_lbl = ImageFont.load_default(size=14)
        except Exception:
            font_title = font_val = font_lbl = ImageFont.load_default()
            
        # Draw Title
        bbox = draw.textbbox((0, 0), "CPU USAGE", font=font_title)
        draw.text(((120 - (bbox[2] - bbox[0])) // 2, 18), "CPU USAGE", fill=(59, 130, 246), font=font_title)
        
        # Draw Value
        val_str = f"{int(self.usage)}%"
        bbox = draw.textbbox((0, 0), val_str, font=font_val)
        draw.text(((120 - (bbox[2] - bbox[0])) // 2, 45), val_str, fill=(255, 255, 255), font=font_val)
        
        # Simple progress bar at the bottom of the key
        draw.rectangle([15, 95, 105, 101], fill=(55, 65, 81))
        fill_w = int(90 * (self.usage / 100.0))
        if fill_w > 0:
            draw.rectangle([15, 95, 15 + fill_w, 101], fill=(34, 197, 94))
            
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()
        
    def draw_segment(self, draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
        # Dial Screen Display
        draw.rectangle([0, 0, width, height], fill=(20, 20, 20))
        
        try:
            font_title = ImageFont.load_default(size=13)
            font_val = ImageFont.load_default(size=15)
        except Exception:
            font_title = font_val = ImageFont.load_default()
            
        draw.text((15, 10), "CPU USAGE", fill=(150, 150, 150), font=font_title)
        
        val_str = f"{self.usage:.1f}%"
        draw.text((15, 30), val_str, fill=(255, 255, 255), font=font_val)
        
        # Progress bar
        draw.rectangle([15, 65, 185, 77], fill=(40, 40, 40))
        fill_w = int(170 * (self.usage / 100.0))
        if fill_w > 0:
            draw.rectangle([15, 65, 15 + fill_w, 77], fill=(59, 130, 246))
