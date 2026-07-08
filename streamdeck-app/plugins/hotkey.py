import io
import subprocess
from PIL import Image, ImageDraw, ImageFont
from plugin_base import KeyPlugin

class HotkeyPlugin(KeyPlugin):
    name = "Custom Hotkey"
    description = "Simulates keyboard hotkeys (e.g., ctrl+alt+t) using xdotool."
    author = "System"
    version = "1.0.0"
    settings_schema = [
        {"name": "label", "label": "Button Label", "type": "text", "default": "Hotkey"},
        {"name": "key_combo", "label": "Key Combo (xdotool format)", "type": "text", "default": "ctrl+alt+t"}
    ]
    
    def __init__(self, settings: dict = None):
        super().__init__(settings)
        self.key_combo = self.settings.get("key_combo", "ctrl+alt+t")
        self.label = self.settings.get("label", "Hotkey")
        
    def get_image(self, state: str) -> bytes:
        bg_color = (67, 56, 202) if state == "PRESSED" else (17, 24, 39)  # Purple pressed, dark gray idle
        img = Image.new("RGB", (120, 120), color=bg_color)
        draw = ImageDraw.Draw(img)
        
        draw.rectangle([3, 3, 116, 116], outline=(31, 41, 55), width=2)
        
        try:
            font_title = ImageFont.load_default(size=14)
            font_combo = ImageFont.load_default(size=11)
            font_lbl = ImageFont.load_default(size=10)
        except Exception:
            font_title = font_combo = font_lbl = ImageFont.load_default()
            
        bbox = draw.textbbox((0, 0), "HOTKEY", font=font_lbl)
        draw.text(((120 - (bbox[2] - bbox[0])) // 2, 15), "HOTKEY", fill=(129, 140, 248), font=font_lbl)
        
        bbox = draw.textbbox((0, 0), self.label, font=font_title)
        draw.text(((120 - (bbox[2] - bbox[0])) // 2, 45), self.label, fill=(255, 255, 255), font=font_title)
        
        bbox = draw.textbbox((0, 0), self.key_combo, font=font_combo)
        draw.text(((120 - (bbox[2] - bbox[0])) // 2, 80), self.key_combo, fill=(156, 163, 175), font=font_combo)
        
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()
        
    def on_press(self):
        try:
            subprocess.run(["xdotool", "key", self.key_combo], check=True)
            print(f"[HOTKEY] Simulated key combo: {self.key_combo}")
        except Exception as e:
            # Fallback output
            print(f"[HOTKEY] Failed simulating key combo: {e} (Is xdotool installed?)")
stream = False
