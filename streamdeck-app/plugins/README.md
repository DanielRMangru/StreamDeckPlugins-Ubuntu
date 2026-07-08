# Stream Deck+ Plugin Development Reference

This directory holds the dynamic plugins for the Stream Deck+ configurator. To add a new control layout, simply create a `.py` file in this directory. The server will discover, import, and serve your plugin's configuration schema to the Web UI automatically at runtime.

---

## Base Class Inheritance

All plugins must import and inherit from either `KeyPlugin` (for buttons) or `DialPlugin` (for rotary knobs and LCD touchscreen segments) defined in `plugin_base.py`.

```python
from plugin_base import KeyPlugin, DialPlugin
```

---

## 1. Defining Configurable Settings

If your plugin needs customization parameters (e.g. application command, hotkey combinations, custom labels, API endpoints), you can declare a `settings_schema` class attribute. The web dashboard will automatically construct form fields for these values on drag-and-drop.

```python
settings_schema = [
    {
        "name": "api_key",        # The key name used in self.settings
        "label": "API Key",       # Form label displayed in the Web UI
        "type": "text",           # Input field type (e.g., text, password)
        "default": "xyz123"       # Default value if left unconfigured
    }
]
```

These parameters will be passed to your plugin's constructor and are available at `self.settings` (e.g., `self.settings.get("api_key")`).

---

## 2. Key Plugin Template (Buttons)

Button plugins occupy one of the 8 visual LCD keys.

```python
import io
from PIL import Image, ImageDraw, ImageFont
from plugin_base import KeyPlugin

class CustomButtonPlugin(KeyPlugin):
    name = "Custom Button"
    description = "Displays custom text and triggers actions on click."
    author = "Developer"
    version = "1.0.0"
    target = "key"  # Explicitly tell the UI it belongs to buttons
    
    # Custom UI settings schema (optional)
    settings_schema = [
        {"name": "label", "label": "Button Text", "type": "text", "default": "Click Me"}
    ]

    def __init__(self, settings: dict = None):
        super().__init__(settings)
        self.label = self.settings.get("label", "Click Me")

    def get_image(self, state: str) -> bytes:
        """
        Generate button image. Must return JPEG bytes (120x120 pixels).
        state can be 'IDLE', 'PRESSED', or 'RELEASED'.
        """
        bg_color = (30, 41, 59) if state != "PRESSED" else (30, 58, 138)
        img = Image.new("RGB", (120, 120), color=bg_color)
        draw = ImageDraw.Draw(img)
        
        # Draw border
        draw.rectangle([3, 3, 116, 116], outline=(71, 85, 105), width=2)
        
        # Render text
        font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), self.label, font=font)
        x = (120 - (bbox[2] - bbox[0])) // 2
        y = (120 - (bbox[3] - bbox[1])) // 2
        draw.text((x, y), self.label, fill=(255, 255, 255), font=font)
        
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()

    def on_press(self):
        """Fires instantly when the key is pressed down."""
        print("Button pressed!")

    def on_release(self):
        """Fires when the key is released."""
        print("Button released!")
        
    def cleanup(self):
        """Called when the plugin is removed or reconfigured."""
        pass
```

---

## 3. Dial Plugin Template (Dials & Screen Segments)

Dial plugins occupy one of the 4 rotary knobs and draw their interface on the 200x100 segment of the LCD touchscreen directly above the knob.

```python
from PIL import ImageDraw, ImageFont
from plugin_base import DialPlugin

class CustomDialPlugin(DialPlugin):
    name = "Custom Dial"
    description = "Controls values by rotating dial; displays status on LCD."
    author = "Developer"
    version = "1.0.0"
    target = "dial"  # Explicitly tell the UI it belongs to dials
    
    def __init__(self, settings: dict = None):
        super().__init__(settings)
        self.value = 50
        
        # Wire up a redraw callback inside your app if values change dynamically in background
        self.redraw_callback = None

    def draw_segment(self, draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
        """
        Draws content on the 200x100 touch LCD screen segment.
        - width: 200 px
        - height: 100 px
        """
        # Clear background
        draw.rectangle([0, 0, width, height], fill=(20, 20, 20))
        
        # Labels
        font = ImageFont.load_default()
        draw.text((15, 15), self.name.upper(), fill=(156, 163, 175), font=font)
        draw.text((15, 40), f"Value: {self.value}", fill=(255, 255, 255), font=font)

    def on_rotate(self, ticks: int, deck):
        """
        Fires when dial is rotated.
        - ticks: Positive for clockwise, negative for counter-clockwise.
        - deck: ThreadSafeDeck hardware handle wrapper.
        """
        self.value = max(0, min(100, self.value + ticks))
        print(f"Dial rotated. New value: {self.value}")

    def on_click(self, pressed: bool, deck):
        """Fires when the dial knob is clicked/pressed."""
        if not pressed:
            print("Dial knob clicked!")

    def on_touch(self, event_type, value: dict, deck):
        """
        Fires when the LCD segment directly above the knob is tapped.
        - event_type: 1 (or 'SHORT') for short tap.
        - value: Position data dict: {'x': x_pos, 'y': y_pos}.
        """
        if event_type == 1 or event_type == "SHORT":
            print(f"LCD touched at position {value}!")
            
    def cleanup(self):
        """Called when the plugin is removed or reconfigured."""
        pass
```
