import io
import subprocess
from PIL import Image, ImageDraw, ImageFont
from plugin_base import KeyPlugin

class AppLauncherPlugin(KeyPlugin):
    name = "App Launcher"
    description = "Launches a custom shell command / application when pressed."
    author = "System"
    version = "1.0.0"
    settings_schema = [
        {"name": "label", "label": "Button Label", "type": "text", "default": "Terminal"},
        {"name": "command", "label": "Shell Command", "type": "text", "default": "gnome-terminal"}
    ]
    
    def __init__(self, settings: dict = None):
        super().__init__(settings)
        # Default settings if none supplied
        self.command = self.settings.get("command", "gnome-terminal")
        self.label = self.settings.get("label", "Terminal")
        
    def get_image(self, state: str) -> bytes:
        bg_color = (20, 83, 45) if state == "PRESSED" else (17, 24, 39)  # Green when pressed, dark gray idle
        img = Image.new("RGB", (120, 120), color=bg_color)
        draw = ImageDraw.Draw(img)
        
        draw.rectangle([3, 3, 116, 116], outline=(31, 41, 55), width=2)
        
        try:
            font_title = ImageFont.load_default(size=15)
            font_cmd = ImageFont.load_default(size=11)
            font_lbl = ImageFont.load_default(size=10)
        except Exception:
            font_title = font_cmd = font_lbl = ImageFont.load_default()
            
        # Draw Launcher title
        bbox = draw.textbbox((0, 0), "LAUNCH", font=font_lbl)
        draw.text(((120 - (bbox[2] - bbox[0])) // 2, 15), "LAUNCH", fill=(34, 197, 94), font=font_lbl)
        
        # Draw app label
        bbox = draw.textbbox((0, 0), self.label, font=font_title)
        draw.text(((120 - (bbox[2] - bbox[0])) // 2, 45), self.label, fill=(255, 255, 255), font=font_title)
        
        # Draw abbreviated command
        cmd_short = self.command.split()[0][:15]
        bbox = draw.textbbox((0, 0), cmd_short, font=font_cmd)
        draw.text(((120 - (bbox[2] - bbox[0])) // 2, 80), cmd_short, fill=(156, 163, 175), font=font_cmd)
        
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()
        
    def on_press(self):
        try:
            # Launch in background asynchronously
            subprocess.Popen(self.command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"[LAUNCHER] Started process: {self.command}")
        except Exception as e:
            print(f"[LAUNCHER] Error starting command: {e}")
