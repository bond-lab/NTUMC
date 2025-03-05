"""
Default configuration for the NTUMC WordNet tagging system.

This module defines the default configuration values used throughout the system.
"""
from typing import Dict, Any


# Default configuration dictionary
DEFAULT_CONFIG: Dict[str, Any] = {
    # Database configuration
    'database': {
        'wordnet_db': 'wn-ntumc.db',
        'corpus_dbs': {
            'eng': ['eng.db'],
            'ces': ['ces.db'],
            'jap': ['jap.db'],
            'zsm': ['zsm.db'],
            'vie': ['vie.db'],
        }
    },
    
    # Tagging configuration
    'tagging': {
        'fallback_lang': 'eng',
        'sid_start': 0,
        'sid_limit': 1000,
        'max_skip': {
            'eng': 3,
            'ces': 1,
            'jap': 1,
            'zsm': 0,
            'vie': 1
        }
    },
    
    # Logging configuration
    'logging': {
        'log_level': 'INFO',
        'log_file': 'logs/ntumc.log',
        'log_format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        'log_date_format': '%Y-%m-%d %H:%M:%S',
        'console_log_level': 'INFO',
        'file_log_level': 'DEBUG',
        'max_file_size': 10485760,  # 10 MB
        'backup_count': 5,
        'propagate': False,
    }
}
