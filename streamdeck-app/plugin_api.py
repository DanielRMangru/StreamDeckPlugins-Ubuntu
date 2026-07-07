"""
Plugin API interface for Stream Deck+ application.
All plugins must inherit from this base class.
"""
from abc import ABC, abstractmethod
from typing import Optional
from PIL import Image


class BasePlugin(ABC):
    """Base class that all Stream Deck plugins must inherit from."""
    
    # Plugin metadata - override these in your plugin
    name: str = "Base Plugin"
    version: str = "1.0.0"
    author: str = "Unknown"
    description: str = "Base plugin class"
    
    def __init__(self, deck_id: str, key_index: int):
        """
        Initialize the plugin.
        
        Args:
            deck_id: Unique identifier for the Stream Deck device
            key_index: The key/index this plugin is bound to (-1 for encoder)
        """
        self.deck_id = deck_id
        self.key_index = key_index
        self.state = {}  # Plugin can store state here
    
    @abstractmethod
    def get_image(self) -> Optional[Image.Image]:
        """
        Generate the image to display on the key/screen.
        
        Returns:
            PIL Image object (72x72 for standard keys) or None for no change
        """
        pass
    
    def on_press(self) -> None:
        """Called when the key/encoder is pressed."""
        pass
    
    def on_release(self) -> None:
        """Called when the key/encoder is released."""
        pass
    
    def on_encoder_rotate(self, ticks: int, pressed: bool) -> None:
        """
        Called when an encoder is rotated (Stream Deck+ only).
        
        Args:
            ticks: Number of ticks rotated (positive=clockwise, negative=counter-clockwise)
            pressed: True if encoder is currently pressed
        """
        pass
    
    def on_context_change(self, context: dict) -> None:
        """
        Called when the plugin context changes (e.g., switching profiles).
        
        Args:
            context: Dictionary containing new context information
        """
        pass
    
    def cleanup(self) -> None:
        """Called when the plugin is being unloaded. Override for cleanup logic."""
        pass
    
    def update_image(self, deck, image: Image.Image) -> None:
        """
        Helper method to update the key image on the deck.
        
        Args:
            deck: StreamDeck device instance
            image: PIL Image to display
        """
        if self.key_index >= 0 and image:
            deck.set_key_image(self.key_index, image.tobytes())
