import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self, config_file: str = "./discadian/config.json"):
        self.config_file = config_file
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                logger.info(f"Configuration loaded from {self.config_file}")
                return config
            else:
                logger.error(f"Configuration file {self.config_file} not found!")
                raise FileNotFoundError(f"Configuration file {self.config_file} not found!")
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON configuration: {e}")
            raise
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            raise
    
    def save_config(self) -> bool:
        """Save current configuration to JSON file"""
        try:
            # Create backup
            if os.path.exists(self.config_file):
                backup_file = f"{self.config_file}.backup"
                with open(self.config_file, 'r', encoding='utf-8') as original:
                    with open(backup_file, 'w', encoding='utf-8') as backup:
                        backup.write(original.read())
            
            # Save new config
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            
            logger.info(f"Configuration saved to {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            return False
    
    def get(self, key: str, default=None):
        """Get a configuration value"""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> bool:
        """Set a configuration value and save"""
        self.config[key] = value
        return self.save_config()
    
    def get_nested(self, *keys, default=None):
        """Get a nested configuration value"""
        current = self.config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current
    
    def set_nested(self, value: Any, *keys) -> bool:
        """Set a nested configuration value and save"""
        current = self.config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
        return self.save_config()
    
    def reload(self):
        """Reload configuration from file"""
        self.config = self._load_config()

# Create global config manager instance
config_manager = ConfigManager()

# API URLs derived from config
API_BASE = config_manager.get_nested("api", "base_url", default="https://api.earthmc.net/v3/aurora")
DISCORD_API_URL = f"{API_BASE}/discord"
PLAYERS_API_URL = f"{API_BASE}/players"
TOWNS_API_URL = f"{API_BASE}/towns"
NATIONS_API_URL = f"{API_BASE}/nations"
CACHE_DURATION = config_manager.get_nested("api", "cache_duration", default=300)