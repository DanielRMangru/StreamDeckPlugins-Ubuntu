import io
import time
import threading
from PIL import Image, ImageDraw, ImageFont
from plugin_base import BasePlugin

class MemUsagePlugin(BasePlugin):
    name = "Memory Usage"
    description = "Displays live RAM usage percentage."
    author = "System"
    version = "1.0.0"
    target = "both"
    
    def __init__(self, settings: dict = None):
        super().__init__(settings)
        self.pct = 0.0
        self.used_gb = 0.0
        self.total_gb = 0.0
        self.running = True
        self.redraw_callback = None
        
        # Start background polling thread
        self.thread = threading.Thread(target=self._poll_mem, daemon=True)
        self.thread.start()
        
    def cleanup(self):
        self.running = False
        
    def _read_meminfo(self):
        try:
            meminfo = {}
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].rstrip(":")
                        val = int(parts[1])  # in kB
                        meminfo[key] = val
            
            total_kb = meminfo.get("MemTotal", 0)
            avail_kb = meminfo.get("MemAvailable", 0)
            
            if total_kb > 0:
                used_kb = total_kb - avail_kb
                pct = (used_kb / total_kb) * 100.0
                
                # Convert to GB (1 GB = 1024 * 1024 KB)
                used_gb = used_kb / (1024 * 1024)
                total_gb = total_kb / (1024 * 1024)
                return used_gb, total_gb, pct
        except Exception as e:
            print(f"[MEM] Error parsing /proc/meminfo: {e}")
        return 0.0, 0.0, 0.0
        
    def _poll_mem(self):
        while self.running:
            self.used_gb, self.total_gb, self.pct = self._read_meminfo()
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
            
        bbox = draw.textbbox((0, 0), "RAM USAGE", font=font_title)
        draw.text(((120 - (bbox[2] - bbox[0])) // 2, 18), "RAM USAGE", fill=(168, 85, 247), font=font_title)
        
        val_str = f"{int(self.pct)}%"
        bbox = draw.textbbox((0, 0), val_str, font=font_val)
        draw.text(((120 - (bbox[2] - bbox[0])) // 2, 45), val_str, fill=(255, 255, 255), font=font_val)
        
        # Draw status bar
        draw.rectangle([15, 95, 105, 101], fill=(55, 65, 81))
        fill_w = int(90 * (self.pct / 100.0))
        if fill_w > 0:
            draw.rectangle([15, 95, 15 + fill_w, 101], fill=(168, 85, 247))
            
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
            
        draw.text((15, 10), "RAM USAGE", fill=(150, 150, 150), font=font_title)
        
        val_str = f"{self.used_gb:.1f} / {self.total_gb:.1f} GB ({self.pct:.1f}%)"
        draw.text((15, 30), val_str, fill=(255, 255, 255), font=font_val)
        
        # Progress bar
        draw.rectangle([15, 65, 185, 77], fill=(40, 40, 40))
        fill_w = int(170 * (self.pct / 100.0))
        if fill_w > 0:
            draw.rectangle([15, 65, 15 + fill_w, 77], fill=(168, 85, 247))
