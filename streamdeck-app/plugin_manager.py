"""
Plugin Manager for Stream Deck+ application.
Handles loading, unloading, and managing plugins.
"""
import os
import sys
import importlib.util
from typing import Dict, Optional, Type
from pathlib import Path

from plugin_api import BasePlugin


class PluginManager:
    """Manages plugin loading, registration, and lifecycle."""
    
    def __init__(self, plugins_dir: str = "plugins"):
        """
        Initialize the plugin manager.
        
        Args:
            plugins_dir: Directory containing plugin files
        """
        self.plugins_dir = Path(plugins_dir)
        self.loaded_plugins: Dict[str, BasePlugin] = {}
        self.plugin_classes: Dict[str, Type[BasePlugin]] = {}
        
        # Ensure plugins directory exists
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        
        # Create __init__.py if it doesn't exist
        init_file = self.plugins_dir / "__init__.py"
        if not init_file.exists():
            init_file.touch()
    
    def discover_plugins(self) -> list:
        """
        Discover all available plugins in the plugins directory.
        
        Returns:
            List of plugin metadata dictionaries
        """
        plugins = []
        
        for file_path in self.plugins_dir.glob("*.py"):
            if file_path.name.startswith("_"):
                continue
            
            try:
                spec = importlib.util.spec_from_file_location(
                    file_path.stem, file_path
                )
                if spec is None or spec.loader is None:
                    continue
                
                module = importlib.util.module_from_spec(spec)
                sys.modules[file_path.stem] = module
                spec.loader.exec_module(module)
                
                # Find plugin classes in the module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        issubclass(attr, BasePlugin) and 
                        attr is not BasePlugin):
                        
                        plugin_info = {
                            "name": attr.name,
                            "version": attr.version,
                            "author": attr.author,
                            "description": attr.description,
                            "class": attr,
                            "module_name": file_path.stem,
                            "class_name": attr_name
                        }
                        plugins.append(plugin_info)
                        self.plugin_classes[attr_name] = attr
                        
            except Exception as e:
                print(f"Error loading plugin from {file_path}: {e}")
        
        return plugins
    
    def load_plugin(self, plugin_class_name: str, deck_id: str, key_index: int) -> Optional[BasePlugin]:
        """
        Load and instantiate a plugin.
        
        Args:
            plugin_class_name: Name of the plugin class to load
            deck_id: Stream Deck device identifier
            key_index: Key index to bind the plugin to
            
        Returns:
            Instantiated plugin or None if loading failed
        """
        if plugin_class_name not in self.plugin_classes:
            print(f"Plugin class {plugin_class_name} not found")
            return None
        
        try:
            plugin_class = self.plugin_classes[plugin_class_name]
            plugin = plugin_class(deck_id, key_index)
            
            plugin_key = f"{deck_id}_{key_index}_{plugin_class_name}"
            self.loaded_plugins[plugin_key] = plugin
            
            print(f"Loaded plugin: {plugin.name} v{plugin.version}")
            return plugin
            
        except Exception as e:
            print(f"Error instantiating plugin {plugin_class_name}: {e}")
            return None
    
    def unload_plugin(self, deck_id: str, key_index: int, plugin_class_name: str) -> bool:
        """
        Unload a plugin from a specific key.
        
        Args:
            deck_id: Stream Deck device identifier
            key_index: Key index
            plugin_class_name: Name of the plugin class
            
        Returns:
            True if successfully unloaded, False otherwise
        """
        plugin_key = f"{deck_id}_{key_index}_{plugin_class_name}"
        
        if plugin_key in self.loaded_plugins:
            try:
                plugin = self.loaded_plugins[plugin_key]
                plugin.cleanup()
                del self.loaded_plugins[plugin_key]
                print(f"Unloaded plugin: {plugin.name}")
                return True
            except Exception as e:
                print(f"Error unloading plugin: {e}")
                return False
        
        return False
    
    def get_plugin(self, deck_id: str, key_index: int, plugin_class_name: str) -> Optional[BasePlugin]:
        """
        Get a loaded plugin instance.
        
        Args:
            deck_id: Stream Deck device identifier
            key_index: Key index
            plugin_class_name: Name of the plugin class
            
        Returns:
            Plugin instance or None if not found
        """
        plugin_key = f"{deck_id}_{key_index}_{plugin_class_name}"
        return self.loaded_plugins.get(plugin_key)
    
    def reload_all_plugins(self) -> None:
        """Reload all plugin modules (useful for development)."""
        # Clear plugin classes
        self.plugin_classes.clear()
        
        # Remove loaded modules from sys.modules
        modules_to_remove = []
        for module_name in sys.modules:
            if module_name not in sys.builtin_module_names:
                try:
                    module_path = getattr(sys.modules[module_name], '__file__', '')
                    if module_path and str(self.plugins_dir) in module_path:
                        modules_to_remove.append(module_name)
                except:
                    pass
        
        for module_name in modules_to_remove:
            del sys.modules[module_name]
        
        # Rediscover plugins
        self.discover_plugins()
        print("Plugins reloaded")
