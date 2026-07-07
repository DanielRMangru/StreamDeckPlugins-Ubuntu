"""
Example plugin: Volume Control
Controls system volume using encoder rotation (Stream Deck+).
"""
import subprocess
from PIL import Image, ImageDraw, ImageFont
from plugin_api import BasePlugin


class VolumePlugin(BasePlugin):
    """Volume control plugin for Stream Deck+ encoders."""
    
    name = "Volume Control"
    version = "1.0.0"
    author = "StreamDeck App"
    description = "Control system volume with encoder"
    
    def __init__(self, deck_id: str, key_index: int):
        super().__init__(deck_id, key_index)
        self.bg_color = (0, 50, 100)  # Blue background
    
    def get_volume(self) -> int:
        """Get current system volume percentage."""
        try:
            result = subprocess.run(
                ['pactl', 'get-sink-volume', '@DEFAULT_SINK@'],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                # Parse output like "Volume: front-left: 45678 /  70%"
                output = result.stdout
                for part in output.split():
                    if '%' in part:
                        return int(part.replace('%', ''))
        except Exception as e:
            print(f"Error getting volume: {e}")
        
        # Fallback: try amixer
        try:
            result = subprocess.run(
                ['amixer', 'get', 'Master'],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                output = result.stdout
                for line in output.split('\n'):
                    if 'Front Left:' in line or 'Mono:' in line:
                        # Parse "[70%]"
                        start = line.find('[')
                        end = line.find('%')
                        if start != -1 and end != -1:
                            return int(line[start+1:end])
        except:
            pass
        
        return 50  # Default fallback
    
    def set_volume(self, volume: int) -> None:
        """Set system volume percentage."""
        volume = max(0, min(100, volume))  # Clamp to 0-100
        
        try:
            subprocess.run(
                ['pactl', 'set-sink-volume', '@DEFAULT_SINK@', f'{volume}%'],
                check=True
            )
        except:
            # Fallback to amixer
            try:
                subprocess.run(
                    ['amixer', 'set', 'Master', f'{volume}%'],
                    check=True
                )
            except Exception as e:
                print(f"Error setting volume: {e}")
    
    def get_image(self) -> Image.Image:
        """Generate an image showing current volume level."""
        image = Image.new('RGB', (72, 72), self.bg_color)
        draw = ImageDraw.Draw(image)
        
        volume = self.get_volume()
        volume_str = f"{volume}%"
        
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        except:
            font = ImageFont.load_default()
        
        # Draw volume icon (simple speaker representation)
        draw.polygon([(10, 20), (10, 52), (25, 52), (35, 62), (35, 10), (25, 20)], 
                    fill=(255, 255, 255))
        
        # Draw volume bars based on level
        bar_count = min(3, max(1, volume // 34))
        for i in range(bar_count):
            bar_height = 10 + (i * 8)
            bar_x = 40 + (i * 8)
            bar_y = 36 - (bar_height // 2)
            draw.rectangle([bar_x, bar_y, bar_x + 4, bar_y + bar_height], 
                          fill=(255, 255, 255))
        
        # Draw volume percentage text
        bbox = draw.textbbox((0, 0), volume_str, font=font)
        text_width = bbox[2] - bbox[0]
        x = (72 - text_width) // 2
        draw.text((x, 55), volume_str, fill=(255, 255, 255), font=font)
        
        return image
    
    def on_encoder_rotate(self, ticks: int, pressed: bool) -> None:
        """Adjust volume when encoder is rotated."""
        if pressed:
            # Mute/unmute when pressed (could be implemented)
            return
        
        # Adjust volume based on rotation direction
        current_volume = self.get_volume()
        new_volume = current_volume + (ticks * 5)  # 5% per tick
        self.set_volume(new_volume)
        print(f"Volume changed to: {new_volume}%")
    
    def on_press(self) -> None:
        """Mute/unmute on press."""
        try:
            subprocess.run(['pactl', 'set-sink-mute', '@DEFAULT_SINK@', 'toggle'], check=True)
            print("Volume toggled mute/unmute")
        except:
            try:
                subprocess.run(['amixer', 'set', 'Master', 'mute', 'toggle'], check=True)
                print("Volume toggled mute/unmute")
            except Exception as e:
                print(f"Error toggling mute: {e}")
