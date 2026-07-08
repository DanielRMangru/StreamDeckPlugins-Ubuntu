# Stream Deck+ Linux Application & Configurator

A python-based web application and daemon for managing the Elgato Stream Deck+ on Linux (Ubuntu 24.04). Features a dynamic drag-and-drop web configuration dashboard, an extensible plugin framework, and thread-safe hardware drivers.

## Features

- **Stunning Web UI**: Drag-and-drop plugins directly onto a visual Stream Deck+ layout (8 keys, LCD touchscreen, 4 dials).
- **Extensible Plugin Framework**: Easily build custom controls for keys or dials/screen zones.
- **Out-of-the-box Controls**:
  - **Clock & Date**: Time display with press-to-toggle date view.
  - **App Launcher**: Starts customizable OS application commands when pressed.
  - **Custom Hotkeys**: Simulates key combination events (via `xdotool`).
  - **Brightness Dial**: Adjusts screen brightness (tap zone to toggle display).
  - **Countdown Timer**: Twist knob to set, press/tap to start/stop, hold to reset, plays sound on completion.
  - **Volume & Mic Control**: Adjusts system output/capture volume and handles mute.
  - **Weather & Pollen**: Shows current local temperature, weather condition (Sun/Rain/Snow/Storm), and AQI/pollen levels using free Open-Meteo APIs (auto-geolocates via public IP; no key needed). Press button or tap screen to toggle.
  - **System Monitors**: Live metric widgets supporting both buttons (keys) and dials/LCD segments:
    - **CPU Usage**: Live CPU utilization percentage.
    - **CPU Temp**: Live CPU core temperature (supports AMD/Intel auto-discovery).
    - **Memory Usage**: Live RAM consumption.
    - **GPU VRAM**: Live GPU VRAM memory allocation (supports AMD/Nvidia).
    - **GPU Temp**: Live GPU core temperature (supports AMD/Nvidia).
- **Thread-safe Daemon Wrapper**: Prevents USB endpoint collisions and hardware freezes using sequential hardware locks.

## Requirements

- Ubuntu 24.04 (or other modern Linux distribution)
- Python 3.10+
- Stream Deck+ device

## Installation

### 1. Install System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y libusb-1.0-0-dev libhidapi-libusb0 libxcb-xinerama0 libxkbcommon-x11-0 xdotool
```

### 2. Set Up UDEV Rules (Allow USB Access)

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

---

## Project Structure

```
streamdeck-app/
├── app.py                  # Main entry point: FastAPI Server + Hardware Daemon
├── plugin_base.py          # Base plugin classes (KeyPlugin, DialPlugin)
├── plugins_config.json     # Saved key and dial configuration mapping
├── plugins/                # Discovered plugin files directory
│   ├── clock.py
│   ├── app_launcher.py
│   ├── hotkey.py
│   ├── brightness.py
│   ├── timer.py
│   ├── volume.py
│   ├── mic.py
│   ├── weather.py
│   ├── cpu_usage.py
│   ├── cpu_temp.py
│   ├── mem_usage.py
│   ├── gpu_vram.py
│   └── gpu_temp.py
├── web/                    # Configurator Frontend
│   ├── index.html
│   ├── index.css
│   └── index.js
└── README.md
```

---

## Usage

### Running the Configurator App

Using `uv` (recommended):
```bash
uv run app.py
```

Using standard Python:
```bash
python3 app.py
```

Once started, open **`http://localhost:8000`** in your browser to access the configuration dashboard.

---

## Creating a New Plugin

Create a new Python file in the `plugins/` directory and extend either `KeyPlugin` or `DialPlugin` from `plugin_base`.

### Key Plugin Example
```python
import io
from PIL import Image, ImageDraw
from plugin_base import KeyPlugin

class MyButtonPlugin(KeyPlugin):
    name = "My Button"
    description = "A custom description"
    author = "Your Name"
    version = "1.0.0"
    
    def get_image(self, state: str) -> bytes:
        # Generate a 120x120 JPEG
        img = Image.new("RGB", (120, 120), color=(20, 30, 40))
        draw = ImageDraw.Draw(img)
        draw.text((10, 50), "Hello", fill=(255, 255, 255))
        
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()
        
    def on_press(self):
        print("Button pressed!")
```

### Dial Plugin Example
```python
from PIL import ImageDraw
from plugin_base import DialPlugin

class MyDialPlugin(DialPlugin):
    name = "My Dial"
    description = "Knob rotary control"
    author = "Your Name"
    version = "1.0.0"
    
    def draw_segment(self, draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
        # Draw on the 200x100 touchscreen segment
        draw.rectangle([0, 0, width, height], fill=(10, 10, 10))
        draw.text((15, 40), "My Dial Control", fill=(255, 255, 255))
        
    def on_rotate(self, ticks: int, deck):
        print(f"Rotated by {ticks}")
```
