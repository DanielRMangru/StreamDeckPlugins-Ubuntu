from PIL import ImageDraw, ImageFont
from plugin_base import DialPlugin

def safe_set_brightness(deck, level):
    try:
        deck.set_brightness(level)
    except Exception as e:
        print(f"[BRIGHTNESS] Warning: could not set hardware brightness ({e})")

class BrightnessPlugin(DialPlugin):
    name = "Brightness Control"
    description = "Adjusts Stream Deck screen brightness. Tap zone to toggle screen on/off."
    author = "System"
    version = "1.0.0"
    
    def __init__(self, settings: dict = None):
        super().__init__(settings)
        self.brightness = self.settings.get("default_brightness", 50)
        self.is_on = True
        self.saved_brightness = 50
        
    def draw_segment(self, draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
        # Base background
        draw.rectangle([0, 0, width, height], fill=(20, 20, 20))
        
        try:
            font_title = ImageFont.load_default(size=13)
            font_val = ImageFont.load_default(size=15)
            font_small = ImageFont.load_default(size=11)
        except Exception:
            font_title = font_val = font_small = ImageFont.load_default()
            
        draw.text((15, 10), "BRIGHTNESS", fill=(150, 150, 150), font=font_title)
        
        if not self.is_on:
            val_text = "OFF"
            text_color = (100, 100, 100)
            pct = 0.0
            bar_color = (50, 50, 50)
        else:
            val_text = f"{self.brightness}%"
            text_color = (255, 255, 255)
            pct = self.brightness / 100.0
            bar_color = (0, 120, 255)
            
        draw.text((15, 30), val_text, fill=text_color, font=font_val)
        
        # Draw progress bar
        draw.rectangle([15, 65, 185, 77], fill=(40, 40, 40))
        fill_w = int(170 * pct)
        if fill_w > 0:
            draw.rectangle([15, 65, 15 + fill_w, 77], fill=bar_color)
            
        # Tap hint
        draw.text((width - 52, height - 16), "[ tap ]", fill=(55, 55, 55), font=font_small)
        
    def on_rotate(self, ticks: int, deck):
        if not self.is_on:
            self.is_on = True
            
        self.brightness = max(10, min(100, self.brightness + (ticks * 5)))
        safe_set_brightness(deck, self.brightness)
        
    def on_click(self, pressed: bool, deck):
        if not pressed:  # On release
            self.toggle(deck)
            
    def on_touch(self, event_type, value: dict, deck):
        # We only handle SHORT tap events
        if event_type == 1 or event_type == "SHORT" or getattr(event_type, "name", "") == "SHORT":
            self.toggle(deck)
            
    def toggle(self, deck):
        if self.is_on:
            self.saved_brightness = self.brightness
            self.brightness = 0
            self.is_on = False
            print("[BRIGHTNESS] Display Toggled: OFF")
        else:
            self.brightness = self.saved_brightness
            self.is_on = True
            print(f"[BRIGHTNESS] Display Toggled: ON ({self.brightness}%)")
        safe_set_brightness(deck, self.brightness)
