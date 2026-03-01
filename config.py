"""
Configuration management for the bot.
"""
import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging

import yaml


class ConfigManager:
    """
    Manages bot configuration loading and saving.
    """
    
    DEFAULT_CONFIG = {
        "loglevel": "info",
        "max-log-files": 5,
        "adb": {
            "host": "127.0.0.1",
            "port": 5555,  # BlueStacks default
        },
        "bot-option": {
            "auto-party-quest": True,
            "pq-timer": 3,
            "auto-growth-after-pq-runs": 50,
            "quest-choice": "sleepywood",
            "solo-option": False,
            "random-jump": True,
        }
    }
    
    def __init__(self, config_path: str = "config/settings.yaml"):
        """
        Initialize configuration manager.
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self.logger = logging.getLogger(__name__)
    
    def load(self) -> Dict[str, Any]:
        """
        Load configuration from file.
        
        Returns:
            Configuration dictionary
        """
        # Start with defaults
        self.config = self.DEFAULT_CONFIG.copy()
        
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    file_config = yaml.safe_load(f)
                
                if file_config:
                    self._merge_config(self.config, file_config)
                    self.logger.info(f"Loaded configuration from {self.config_path}")
            
            except yaml.YAMLError as e:
                self.logger.error(f"Error parsing config file: {e}")
            except Exception as e:
                self.logger.error(f"Error loading config: {e}")
        else:
            self.logger.warning(f"Config file not found: {self.config_path}")
            self.logger.info("Using default configuration")
            self.save()  # Create default config file
        
        return self.config
    
    def save(self) -> bool:
        """
        Save current configuration to file.
        
        Returns:
            True if saved successfully
        """
        try:
            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
            
            self.logger.info(f"Configuration saved to {self.config_path}")
            return True
        
        except Exception as e:
            self.logger.error(f"Error saving config: {e}")
            return False
    
    def _merge_config(self, base: Dict, override: Dict):
        """Recursively merge override config into base."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        
        Args:
            key: Configuration key (supports dot notation: "adb.port")
            default: Default value if key not found
        
        Returns:
            Configuration value
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """
        Set a configuration value.
        
        Args:
            key: Configuration key (supports dot notation)
            value: Value to set
        """
        keys = key.split('.')
        config = self.config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
    
    def get_bot_options(self) -> Dict[str, Any]:
        """Get bot-specific options."""
        return self.config.get("bot-option", {})
    
    def get_adb_config(self) -> Dict[str, Any]:
        """Get ADB configuration."""
        return self.config.get("adb", {})


def create_default_config(path: str = "config/settings.yaml"):
    """Create a default configuration file with comments."""
    config_content = """# MapleStory Idle Bot Configuration
# ══════════════════════════════════════════════════════════════════════════════

# Logging level: debug | info | warning | error
loglevel: info

# Keep only this many most recent log files (0 = keep all)
max-log-files: 5

# ──────────────────────────────────────────────────────────────────────────────
# ADB Connection Settings
# ──────────────────────────────────────────────────────────────────────────────
adb:
  host: "127.0.0.1"
  # BlueStacks ports: 5555, 5565, 5575, 5585 (check Advanced settings)
  port: 5555

# ──────────────────────────────────────────────────────────────────────────────
# Bot Options
# ──────────────────────────────────────────────────────────────────────────────
bot-option:
  # Auto party quest: true | false
  auto-party-quest: true
  
  # Time in minutes before bot cancels and re-queues
  pq-timer: 3
  
  # Auto growth check
  # Options: 0 = disabled | 1 = after 1 run | 50 = after 50 runs, etc.
  auto-growth-after-pq-runs: 50
  
  # Quest options: sleepywood | ludibrium | zakum | orbis
  quest-choice: sleepywood
  
  # Solo mode: true | false
  solo-option: false
  
  # Random jump (anti-detection): true | false
  random-jump: true

# ──────────────────────────────────────────────────────────────────────────────
# Advanced Settings
# ──────────────────────────────────────────────────────────────────────────────
advanced:
  # Screenshot cache duration (seconds)
  screenshot-cache: 0.1
  
  # Template matching threshold (0.0 - 1.0)
  match-threshold: 0.85
  
  # Input humanization
  humanize-input: true
  tap-offset-range: 5  # Random pixel offset

# ══════════════════════════════════════════════════════════════════════════════
"""
    
    filepath = Path(path)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(config_content)
    
    print(f"Created default configuration at: {filepath}")


if __name__ == "__main__":
    create_default_config()

