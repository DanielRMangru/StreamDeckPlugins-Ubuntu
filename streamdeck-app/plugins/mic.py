import subprocess
from PIL import ImageDraw, ImageFont
from plugin_base import DialPlugin

def run_amixer(command_args):
    try:
        subprocess.run(["amixer", "-q"] + command_args, check=True)
    except Exception as e:
        print(f"[MIC] amixer control error: {e}")

class MicVolumePlugin(DialPlugin):
    name = "Microphone Volume"
    description = "Controls mic capture volume with dial, click/tap to toggle mute."
    author = "System"
    version = "1.0.0"
    
    def __init__(self, settings: dict = None):
        super().__init__(settings)
        self.volume = self.settings.get("default_volume", 75)
        self.is_muted = False
        
    def draw_segment(self, draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
        draw.rectangle([0, 0, width, height], fill=(20, 20, 20))
        
        try:
            font_title = ImageFont.load_default(size=13)
            font_val = ImageFont.load_default(size=15)
            font_small = ImageFont.load_default(size=11)
        except Exception:
            font_title = font_val = font_small = ImageFont.load_default()
            
        draw.text((15, 10), "MIC", fill=(150, 150, 150), font=font_title)
        
        if self.is_muted:
            val_text = "MUTED"
            text_color = (255, 100, 100)
            pct = self.volume / 100.0
            bar_color = (100, 30, 30)
        else:
            val_text = f"{self.volume}%"
            text_color = (255, 255, 255)
            pct = self.volume / 100.0
            bar_color = (200, 50, 200)  # Mic purple accent
            
        draw.text((15, 30), val_text, fill=text_color, font=font_val)
        
        # Progress bar
        draw.rectangle([15, 65, 185, 77], fill=(40, 40, 40))
        fill_w = int(170 * pct)
        if fill_w > 0:
            draw.rectangle([15, 65, 15 + fill_w, 77], fill=bar_color)
            
        draw.text((width - 52, height - 16), "[ tap ]", fill=(55, 55, 55), font=font_small)
        
    def on_rotate(self, ticks: int, deck):
        self.is_muted = False
        self.volume = max(0, min(100, self.volume + ticks * 2))
        direction = f"{abs(ticks * 2)}%+" if ticks > 0 else f"{abs(ticks * 2)}%-"
        run_amixer(["set", "Capture", direction])
        
    def on_click(self, pressed: bool, deck):
        if not pressed:  # Toggle on release
            self.toggle_mute()
            
    def on_touch(self, event_type, value: dict, deck):
        if event_type == 1 or event_type == "SHORT" or getattr(event_type, "name", "") == "SHORT":
            self.toggle_mute()
            
    def toggle_mute(self):
        self.is_muted = not self.is_muted
        run_amixer(["set", "Capture", "toggle"])
        print(f"[MIC] Mute state toggled to: {self.is_muted}")
