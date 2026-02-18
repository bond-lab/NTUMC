"""
Configuration loader for the NTUMC WordNet tagging system.

This module provides functions for loading and managing configuration settings.
"""
import os
import sys
import json
import yaml
from typing import Dict, Any, Optional

from ntumc.config.default_config import DEFAULT_CONFIG
from ntumc.core.logging_setup import setup_logging


def load_config(config_file: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from file and merge with defaults.
    
    Args:
        config_file: Path to configuration file (JSON or YAML)
        
    Returns:
        Dict[str, Any]: Configuration dictionary
    """
    # Start with default configuration
    config = DEFAULT_CONFIG.copy()
    
    # Load from file if specified
    if config_file and os.path.exists(config_file):
        file_config = _load_config_file(config_file)
        if file_config:
            config = _merge_configs(config, file_config)
    
    return config


def _load_config_file(config_file: str) -> Dict[str, Any]:
    """
    Load configuration from a file.
    
    Supports JSON and YAML formats based on file extension.
    
    Args:
        config_file: Path to configuration file
        
    Returns:
        Dict[str, Any]: Configuration from file
    """
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            if config_file.endswith('.json'):
                return json.load(f)
            elif config_file.endswith(('.yaml', '.yml')):
                return yaml.safe_load(f)
            else:
                print(f"Unsupported configuration file format: {config_file}")
                return {}
    except Exception as e:
        print(f"Error loading configuration file {config_file}: {e}")
        return {}


def _merge_configs(base_config: Dict[str, Any], override_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively merge two configuration dictionaries.
    
    Values in override_config take precedence over values in base_config.
    
    Args:
        base_config: Base configuration
        override_config: Configuration to override base with
        
    Returns:
        Dict[str, Any]: Merged configuration
    """
    result = base_config.copy()
    
    for key, value in override_config.items():
        # If both values are dictionaries, merge them recursively
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_configs(result[key], value)
        else:
            # Otherwise, override the base value
            result[key] = value
    
    return result


def initialize_logging(config: Dict[str, Any]) -> None:
    """
    Initialize logging based on configuration.
    
    Args:
        config: Configuration dictionary
    """
    # Extract logging configuration
    logging_config = config.get('logging', {})
    
    # Set up logging
    setup_logging(logging_config)
