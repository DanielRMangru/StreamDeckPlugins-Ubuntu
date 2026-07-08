import io
from PIL import Image, ImageDraw, ImageFont

class BasePlugin:
    """Base class for all plugins."""
    name: str = "Base Plugin"
    description: str = "Base description"
    author: str = "Unknown"
    version: str = "1.0.0"
    target: str = "key"  # Must be "key" or "dial"
    settings_schema: list = []  # List of dicts: [{"name": "param", "label": "Label", "type": "text", "default": "value"}]
    
    def __init__(self, settings: dict = None):
        self.settings = settings or {}
        
    def cleanup(self):
        """Called when plugin is unloaded."""
        pass


class KeyPlugin(BasePlugin):
    """Plugin designed for Stream Deck LCD buttons."""
    target = "key"
    
    def get_image(self, state: str) -> bytes:
        """
        Generate key image.
        Returns JPEG bytes (120x120 pixels).
        """
        img = Image.new("RGB", (120, 120), color=(30, 30, 30))
        draw = ImageDraw.Draw(img)
        draw.text((10, 50), self.name[:15], fill=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()
        
    def on_press(self):
        """Called when button is pressed down."""
        pass
        
    def on_release(self):
        """Called when button is released."""
        pass
        
    def on_hold(self):
        """Called when button is held down beyond hold threshold."""
        pass


class DialPlugin(BasePlugin):
    """Plugin designed for Stream Deck dials and touchscreen segments."""
    target = "dial"
    
    def draw_segment(self, draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
        """
        Draw on the corresponding 200x100 touchscreen segment.
        """
        draw.text((15, 15), self.name[:20], fill=(150, 150, 150))
        draw.text((15, 45), "Active", fill=(255, 255, 255))
        
    def on_rotate(self, ticks: int):
        """Called when dial is rotated."""
        pass
        
    def on_click(self, pressed: bool):
        """Called when dial button is pressed or released."""
        pass
        
    def on_touch(self, event_type, value: dict):
        """Called when touchscreen segment is tapped/swiped."""
        pass
