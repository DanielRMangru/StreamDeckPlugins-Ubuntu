"""
Main Stream Deck+ Application
Handles device connection, event loop, and plugin management.
"""
import sys
import time
import signal
from typing import Dict, Optional

from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.ImageHelpers import PILHelper

from plugin_manager import PluginManager
from plugin_api import BasePlugin


class StreamDeckApp:
    """Main application class for Stream Deck+ control."""
    
    def __init__(self):
        """Initialize the Stream Deck application."""
        self.deck: Optional[any] = None
        self.plugin_manager = PluginManager()
        self.key_plugins: Dict[int, BasePlugin] = {}
        self.encoder_plugins: Dict[int, BasePlugin] = {}
        self.running = False
        
        # Discover available plugins
        print("Discovering plugins...")
        plugins = self.plugin_manager.discover_plugins()
        for plugin in plugins:
            print(f"  Found: {plugin['name']} v{plugin['version']} by {plugin['author']}")
    
    def connect(self) -> bool:
        """
        Connect to a Stream Deck device.
        
        Returns:
            True if connected successfully, False otherwise
        """
        try:
            decks = DeviceManager().enumerate()
            
            if not decks:
                print("No Stream Deck devices found.")
                return False
            
            # Use the first available deck
            self.deck = decks[0]
            self.deck.open()
            self.deck.reset()
            
            print(f"\nConnected to: {self.deck.deck_type()}")
            print(f"  Key count: {self.deck.key_count()}")
            print(f"  Key image size: {self.deck.key_image_format()['size']}")
            print(f"  Has encoders: {self.deck.encoder_count() > 0}")
            if self.deck.encoder_count() > 0:
                print(f"  Encoder count: {self.deck.encoder_count()}")
            
            # Set up callback handlers
            self.deck.set_key_callback(self._on_key_press)
            self.deck.set_encoder_callback(self._on_encoder_event)
            
            return True
            
        except Exception as e:
            print(f"Error connecting to Stream Deck: {e}")
            return False
    
    def _on_key_press(self, deck, key, state):
        """
        Handle key press events.
        
        Args:
            deck: StreamDeck device instance
            key: Key index that was pressed
            state: Key state (True=pressed, False=released)
        """
        if key in self.key_plugins:
            plugin = self.key_plugins[key]
            if state:
                plugin.on_press()
                self._update_key_image(key, plugin)
            else:
                plugin.on_release()
    
    def _on_encoder_event(self, deck, encoder, ticks, state):
        """
        Handle encoder events (Stream Deck+ only).
        
        Args:
            deck: StreamDeck device instance
            encoder: Encoder index
            ticks: Number of ticks rotated (positive=clockwise)
            state: Encoder state (True=pressed, False=released)
        """
        if encoder in self.encoder_plugins:
            plugin = self.encoder_plugins[encoder]
            plugin.on_encoder_rotate(ticks, state)
            self._update_encoder_image(encoder, plugin)
        elif state:  # Only handle press for unbound encoders
            # Could add default behavior here
            pass
    
    def _update_key_image(self, key: int, plugin: BasePlugin):
        """Update the image for a specific key."""
        if self.deck is None:
            return
        
        try:
            image = plugin.get_image()
            if image:
                # Convert to format expected by Stream Deck
                source_image = PILHelper.to_native_format(self.deck, image)
                self.deck.set_key_image(key, source_image)
        except Exception as e:
            print(f"Error updating key {key} image: {e}")
    
    def _update_encoder_image(self, encoder: int, plugin: BasePlugin):
        """Update the image for a specific encoder screen."""
        if self.deck is None:
            return
        
        try:
            image = plugin.get_image()
            if image:
                # Encoder screens are typically 128x128 or similar
                source_image = PILHelper.to_native_format(self.deck, image)
                self.deck.set_encoder_image(encoder, source_image)
        except Exception as e:
            print(f"Error updating encoder {encoder} image: {e}")
    
    def assign_plugin(self, plugin_class_name: str, key_index: int, is_encoder: bool = False):
        """
        Assign a plugin to a key or encoder.
        
        Args:
            plugin_class_name: Name of the plugin class to assign
            key_index: Index of the key/encoder
            is_encoder: True if assigning to an encoder, False for a key
        """
        deck_id = str(id(self.deck)) if self.deck else "unknown"
        
        plugin = self.plugin_manager.load_plugin(plugin_class_name, deck_id, key_index)
        if plugin is None:
            return
        
        if is_encoder:
            self.encoder_plugins[key_index] = plugin
            self._update_encoder_image(key_index, plugin)
            print(f"Assigned {plugin.name} to encoder {key_index}")
        else:
            self.key_plugins[key_index] = plugin
            self._update_key_image(key_index, plugin)
            print(f"Assigned {plugin.name} to key {key_index}")
    
    def update_all_images(self):
        """Update images on all keys and encoders."""
        for key, plugin in self.key_plugins.items():
            self._update_key_image(key, plugin)
        
        for encoder, plugin in self.encoder_plugins.items():
            self._update_encoder_image(encoder, plugin)
    
    def run(self):
        """Run the main application loop."""
        if not self.connect():
            return
        
        self.running = True
        
        # Example setup: assign plugins to keys/encoders
        # In a real app, this would be configured via UI or config file
        print("\nSetting up example configuration...")
        
        # Assign clock plugin to first key
        if self.deck.key_count() > 0:
            self.assign_plugin("ClockPlugin", 0, is_encoder=False)
        
        # Assign volume plugin to first encoder (if available)
        if self.deck.encoder_count() > 0:
            self.assign_plugin("VolumePlugin", 0, is_encoder=True)
        
        print("\nApplication running. Press Ctrl+C to exit.")
        
        # Main loop - periodically update dynamic plugins
        try:
            while self.running:
                # Update clock every second
                for key, plugin in list(self.key_plugins.items()):
                    if isinstance(plugin, type(self.key_plugins.get(0))) and hasattr(plugin, 'state'):
                        mode = plugin.state.get('mode', 'time')
                        if mode == 'time':
                            self._update_key_image(key, plugin)
                
                # Update volume display
                for encoder, plugin in self.encoder_plugins.items():
                    self._update_encoder_image(encoder, plugin)
                
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources and close the device."""
        self.running = False
        
        # Cleanup all plugins
        for plugin in list(self.key_plugins.values()) + list(self.encoder_plugins.values()):
            try:
                plugin.cleanup()
            except:
                pass
        
        # Close the deck
        if self.deck and self.deck.is_open():
            try:
                self.deck.reset()
                self.deck.close()
                print("Stream Deck closed.")
            except:
                pass


def main():
    """Main entry point."""
    print("=" * 50)
    print("Stream Deck+ Linux Application")
    print("=" * 50)
    
    app = StreamDeckApp()
    
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        app.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    app.run()


if __name__ == "__main__":
    main()
