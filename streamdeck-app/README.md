# Stream Deck+ Linux Application

A Python-based application for controlling the Elgato Stream Deck+ on Linux (Ubuntu 24.04). This application provides a plugin system that allows you to create custom plugins for keys and encoders.

## Features

- **Full Stream Deck+ Support**: Works with all 8 LCD keys and 4 touch-sensitive encoders
- **Plugin System**: Create custom plugins by extending a simple base class
- **Encoder Support**: Handle rotary encoder events (rotate, press)
- **Dynamic Updates**: Plugins can update their display in real-time
- **Easy Development**: Hot-reload plugins during development

## Requirements

- Ubuntu 24.04 (or other modern Linux distribution)
- Python 3.10+
- Stream Deck+ device

## Installation

### 1. Install System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y libusb-1.0-0-dev libhidapi-libusb0 libxcb-xinerama0 libxkbcommon-x11-0 libegl1 libopengl0
```

### 2. Install Python Dependencies

```bash
pip3 install streamdeck Pillow PyQt6
```

### 3. Set Up UDEV Rules (Required for USB Access)

Create a udev rule to allow non-root access to the Stream Deck:

```bash
sudo tee /etc/udev/rules.d/70-streamdeck.rules << EOF
SUBSYSTEM=="usb", ATTRS{idVendor}=="0fd9", MODE="0666"
EOF
```

Then reload udev rules:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## Project Structure

```
streamdeck-app/
├── main.py              # Main application entry point
├── plugin_api.py        # Base plugin class (extend this for new plugins)
├── plugin_manager.py    # Plugin discovery and lifecycle management
├── plugins/             # Directory for your custom plugins
│   ├── __init__.py
│   ├── clock_plugin.py  # Example: Clock display plugin
│   └── volume_plugin.py # Example: Volume control plugin
└── README.md
```

## Usage

### Running the Application

```bash
cd streamdeck-app
python3 main.py
```

**Note**: You may need to run with `sudo` if udev rules aren't set up correctly, but it's recommended to set up udev rules instead.

### Creating a New Plugin

1. Create a new Python file in the `plugins/` directory
2. Extend the `BasePlugin` class from `plugin_api`
3. Implement at minimum the `get_image()` method

#### Example Plugin Template

```python
from plugin_api import BasePlugin
from PIL import Image, ImageDraw

class MyPlugin(BasePlugin):
    name = "My Plugin"
    version = "1.0.0"
    author = "Your Name"
    description = "Description of what your plugin does"
    
    def get_image(self) -> Image.Image:
        """Generate the image to display on the key."""
        image = Image.new('RGB', (72, 72), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.text((10, 30), "Hello!", fill=(255, 255, 255))
        return image
    
    def on_press(self) -> None:
        """Called when the key is pressed."""
        print("Key pressed!")
    
    def on_encoder_rotate(self, ticks: int, pressed: bool) -> None:
        """Called when encoder is rotated (for Stream Deck+)."""
        print(f"Encoder rotated by {ticks} ticks")
```

### Plugin API Reference

#### BasePlugin Methods

| Method | Description |
|--------|-------------|
| `get_image()` | Return a PIL Image (72x72 for keys) to display |
| `on_press()` | Called when key/encoder is pressed |
| `on_release()` | Called when key/encoder is released |
| `on_encoder_rotate(ticks, pressed)` | Called when encoder rotates |
| `on_context_change(context)` | Called when context/profile changes |
| `cleanup()` | Called when plugin is unloaded |

#### Plugin Metadata

Set these class attributes in your plugin:

- `name`: Display name of the plugin
- `version`: Version string
- `author`: Author name
- `description`: Brief description

## Included Example Plugins

### Clock Plugin (`clock_plugin.py`)
- Displays current time on a key
- Press to toggle between time and date display

### Volume Plugin (`volume_plugin.py`)
- Shows current system volume level
- Rotate encoder to adjust volume (Stream Deck+)
- Press encoder to mute/unmute
- Requires `pactl` or `amixer` (PulseAudio/ALSA)

## Troubleshooting

### "No Stream Deck devices found"
1. Ensure the device is plugged in
2. Check udev rules are set up correctly
3. Try running with `sudo` temporarily to test

### Permission Denied Errors
Set up the udev rules as described in the Installation section.

### Module Import Errors
Ensure you're running from the `streamdeck-app` directory:
```bash
cd streamdeck-app
python3 main.py
```

## Architecture

The application consists of three main components:

1. **Main Application** (`main.py`): Handles device connection, event loop, and plugin assignment
2. **Plugin Manager** (`plugin_manager.py`): Discovers, loads, and manages plugin lifecycle
3. **Plugin API** (`plugin_api.py`): Defines the interface that all plugins must implement

## License

MIT License - Feel free to use and modify for your own projects!
