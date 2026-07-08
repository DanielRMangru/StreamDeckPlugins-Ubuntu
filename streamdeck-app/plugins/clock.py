import io
import time
import threading
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from plugin_base import KeyPlugin

class ClockPlugin(KeyPlugin):
    name = "Clock & Date"
    description = "Displays the current time. Press to toggle date."
    author = "System"
    version = "1.0.0"
    
    def __init__(self, settings: dict = None):
        super().__init__(settings)
        self.mode = "time"  # "time" or "date"
        self.running = True
        self.redraw_callback = None
        self.thread = threading.Thread(target=self._poll_clock, daemon=True)
        self.thread.start()
        
    def cleanup(self):
        self.running = False
        
    def _poll_clock(self):
        while self.running:
            time.sleep(1.0)
            if getattr(self, "redraw_callback", None):
                self.redraw_callback()
                
    def get_image(self, state: str) -> bytes:
        img = Image.new("RGB", (120, 120), color=(15, 23, 42))  # slate-900
        draw = ImageDraw.Draw(img)
        
        # Inner border
        draw.rectangle([3, 3, 116, 116], outline=(30, 41, 59), width=2)
        
        now = datetime.now()
        if self.mode == "time":
            main_text = now.strftime("%H:%M")
            sub_text = ""
            label_text = "CLOCK"
            main_y = 45
        else:
            main_text = now.strftime("%d")
            sub_text = now.strftime("%b").upper()
            label_text = "DATE"
            main_y = 35
            
        try:
            font_main = ImageFont.load_default(size=26)
            font_sub = ImageFont.load_default(size=14)
            font_lbl = ImageFont.load_default(size=11)
        except Exception:
            font_main = font_sub = font_lbl = ImageFont.load_default()
            
        # Draw main text
        bbox = draw.textbbox((0, 0), main_text, font=font_main)
        tw = bbox[2] - bbox[0]
        draw.text(((120 - tw) // 2, main_y), main_text, fill=(248, 250, 252), font=font_main)
        
        # Draw sub text
        if sub_text:
            bbox_sub = draw.textbbox((0, 0), sub_text, font=font_sub)
            tsw = bbox_sub[2] - bbox_sub[0]
            draw.text(((120 - tsw) // 2, 70), sub_text, fill=(148, 163, 184), font=font_sub)
        
        # Label at top
        bbox_lbl = draw.textbbox((0, 0), label_text, font=font_lbl)
        tlw = bbox_lbl[2] - bbox_lbl[0]
        draw.text(((120 - tlw) // 2, 12), label_text, fill=(59, 130, 246), font=font_lbl)
        
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()
        
    def on_press(self):
        self.mode = "date" if self.mode == "time" else "time"
        if self.redraw_callback:
            self.redraw_callback()
