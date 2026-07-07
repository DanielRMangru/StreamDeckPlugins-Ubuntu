"""
Example plugin: Clock
Displays the current time on a Stream Deck key.
"""
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from plugin_api import BasePlugin


class ClockPlugin(BasePlugin):
    """A simple clock plugin that displays the current time."""
    
    name = "Clock"
    version = "1.0.0"
    author = "StreamDeck App"
    description = "Displays the current time"
    
    def __init__(self, deck_id: str, key_index: int):
        super().__init__(deck_id, key_index)
        self.bg_color = (0, 0, 0)  # Black background
        self.text_color = (255, 255, 255)  # White text
    
    def get_image(self) -> Image.Image:
        """Generate an image showing the current time."""
        # Create a 72x72 image (standard Stream Deck key size)
        image = Image.new('RGB', (72, 72), self.bg_color)
        draw = ImageDraw.Draw(image)
        
        # Get current time
        now = datetime.now()
        time_str = now.strftime("%H:%M")
        
        # Try to use a default font, fall back to default if not available
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        except:
            font = ImageFont.load_default()
        
        # Calculate text bounding box and center it
        bbox = draw.textbbox((0, 0), time_str, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = (72 - text_width) // 2
        y = (72 - text_height) // 2
        
        # Draw the time
        draw.text((x, y), time_str, fill=self.text_color, font=font)
        
        return image
    
    def on_press(self) -> None:
        """Toggle between time and date display on press."""
        current_mode = self.state.get('mode', 'time')
        self.state['mode'] = 'date' if current_mode == 'time' else 'time'
        print(f"Clock plugin mode switched to: {self.state['mode']}")
    
    def get_date_image(self) -> Image.Image:
        """Generate an image showing the current date."""
        image = Image.new('RGB', (72, 72), self.bg_color)
        draw = ImageDraw.Draw(image)
        
        now = datetime.now()
        date_str = now.strftime("%m/%d")
        
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        except:
            font = ImageFont.load_default()
        
        bbox = draw.textbbox((0, 0), date_str, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = (72 - text_width) // 2
        y = (72 - text_height) // 2
        
        draw.text((x, y), date_str, fill=self.text_color, font=font)
        
        return image
