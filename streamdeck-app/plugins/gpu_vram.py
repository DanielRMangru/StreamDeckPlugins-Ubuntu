import io
import time
import glob
import subprocess
import threading
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from plugin_base import BasePlugin

class GpuVramPlugin(BasePlugin):
    name = "GPU VRAM"
    description = "Displays live GPU VRAM usage (supports AMD & Nvidia)."
    author = "System"
    version = "1.0.0"
    target = "both"
    
    def __init__(self, settings: dict = None):
        super().__init__(settings)
        self.used_gb = 0.0
        self.total_gb = 0.0
        self.pct = 0.0
        self.running = True
        self.redraw_callback = None
        
        # Discover card
        self.amd_total_path = None
        self.amd_used_path = None
        self._discover_amd_paths()
        
        # Start background polling thread
        self.thread = threading.Thread(target=self._poll_vram, daemon=True)
        self.thread.start()
        
    def cleanup(self):
        self.running = False
        
    def _discover_amd_paths(self):
        totals = glob.glob("/sys/class/drm/card*/device/mem_info_vram_total")
        if totals:
            self.amd_total_path = Path(totals[0])
            self.amd_used_path = self.amd_total_path.parent / "mem_info_vram_used"
            print(f"[GPU VRAM] Discovered AMD VRAM node: {self.amd_total_path}")
            
    def _read_vram(self):
        # 1. AMD sysfs method
        if self.amd_total_path and self.amd_used_path and self.amd_total_path.exists() and self.amd_used_path.exists():
            try:
                with open(self.amd_total_path, "r") as f:
                    total_bytes = float(f.read().strip())
                with open(self.amd_used_path, "r") as f:
                    used_bytes = float(f.read().strip())
                
                if total_bytes > 0:
                    pct = (used_bytes / total_bytes) * 100.0
                    used_gb = used_bytes / (1024**3)
                    total_gb = total_bytes / (1024**3)
                    return used_gb, total_gb, pct
            except:
                pass
                
        # 2. Nvidia fallback via nvidia-smi
        try:
            res = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,nounits,noheader"],
                capture_output=True, text=True
            )
            if res.returncode == 0:
                parts = res.stdout.strip().split(",")
                if len(parts) >= 2:
                    used_mb = float(parts[0].strip())
                    total_mb = float(parts[1].strip())
                    pct = (used_mb / total_mb) * 100.0
                    return used_mb / 1024.0, total_mb / 1024.0, pct
        except:
            pass
            
        return 0.0, 0.0, 0.0
        
    def _poll_vram(self):
        while self.running:
            self.used_gb, self.total_gb, self.pct = self._read_vram()
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
        except Exception:
            font_title = font_val = ImageFont.load_default()
            
        bbox = draw.textbbox((0, 0), "GPU VRAM", font=font_title)
        draw.text(((120 - (bbox[2] - bbox[0])) // 2, 18), "GPU VRAM", fill=(16, 185, 129), font=font_title)
        
        val_str = f"{int(self.pct)}%"
        bbox = draw.textbbox((0, 0), val_str, font=font_val)
        draw.text(((120 - (bbox[2] - bbox[0])) // 2, 45), val_str, fill=(255, 255, 255), font=font_val)
        
        # Draw status bar
        draw.rectangle([15, 95, 105, 101], fill=(55, 65, 81))
        fill_w = int(90 * (self.pct / 100.0))
        if fill_w > 0:
            draw.rectangle([15, 95, 15 + fill_w, 101], fill=(16, 185, 129))
            
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
            
        draw.text((15, 10), "GPU VRAM", fill=(150, 150, 150), font=font_title)
        
        val_str = f"{self.used_gb:.1f} / {self.total_gb:.1f} GB ({self.pct:.1f}%)"
        draw.text((15, 30), val_str, fill=(255, 255, 255), font=font_val)
        
        # Progress bar
        draw.rectangle([15, 65, 185, 77], fill=(40, 40, 40))
        fill_w = int(170 * (self.pct / 100.0))
        if fill_w > 0:
            draw.rectangle([15, 65, 15 + fill_w, 77], fill=(16, 185, 129))
