"""
Logging setup for the NTUMC WordNet tagging system.

This module provides functions for configuring logging and utilities
for common logging patterns.
"""
import os
import sys
import logging
import functools
import traceback
from typing import Any, Callable, Dict, Optional, Union, List, TypeVar, cast
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path

# Type variables for function decorators
F = TypeVar('F', bound=Callable[..., Any])


# Default logging configuration
DEFAULT_CONFIG = {
    'log_level': 'INFO',
    'log_file': None,  # Changed to None by default to avoid creating files unnecessarily
    'log_format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'log_date_format': '%Y-%m-%d %H:%M:%S',
    'console_log_level': 'INFO',
    'file_log_level': 'DEBUG',
    'max_file_size': 10485760,  # 10 MB
    'backup_count': 5,
    'propagate': False,
}


def setup_logging(config: Optional[Dict[str, Any]] = None) -> logging.Logger:
    """
    Set up logging for the NTUMC WordNet tagging system.
    
    Args:
        config: Configuration dictionary. If None, default configuration is used.
            Supported keys:
            - log_level: Overall logging level
            - log_file: Path to log file
            - log_format: Format string for log messages
            - log_date_format: Format string for log timestamps
            - console_log_level: Logging level for console output
            - file_log_level: Logging level for file output
            - max_file_size: Maximum size of log file before rotation
            - backup_count: Number of backup files to keep
            - propagate: Whether to propagate logs to parent loggers
    
    Returns:
        logging.Logger: Configured root logger for the NTUMC system
    """
    # Use default config if none provided
    if config is None:
        config = DEFAULT_CONFIG.copy()
    else:
        # Fill in missing values with defaults
        full_config = DEFAULT_CONFIG.copy()
        full_config.update(config)
        config = full_config
    
    # Create root logger for the NTUMC system
    logger = logging.getLogger('ntumc')
    
    # Clear any existing handlers and properly close file handlers
    if logger.handlers:
        for handler in logger.handlers:
            # Properly close file handlers
            if isinstance(handler, logging.FileHandler):
                handler.close()
        logger.handlers.clear()
    
    # Set overall log level
    log_level = config.get('log_level', 'INFO')
    level = get_log_level(log_level)
    logger.setLevel(level)
    
    # Configure log format
    log_format = config.get('log_format', DEFAULT_CONFIG['log_format'])
    date_format = config.get('log_date_format', DEFAULT_CONFIG['log_date_format'])
    formatter = logging.Formatter(log_format, date_format)
    
    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_level = get_log_level(config.get('console_log_level', 'INFO'))
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Add file handler if log_file is specified and not None
    log_file = config.get('log_file')
    if log_file:
        # Create directory if it doesn't exist
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        file_level = get_log_level(config.get('file_log_level', 'DEBUG'))
        max_size = config.get('max_file_size', 10485760)  # 10 MB
        backup_count = config.get('backup_count', 5)
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_size,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(file_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # Set propagation
    logger.propagate = config.get('propagate', False)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a module-specific logger.
    
    Args:
        name: Name of the module or component
        
    Returns:
        logging.Logger: Logger for the specified module
    """
    return logging.getLogger(f'ntumc.{name}')


def get_log_level(level: Union[str, int]) -> int:
    """
    Convert a log level name to its numeric value.
    
    Args:
        level: Log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL)
               or numeric value
    
    Returns:
        int: Numeric log level
    """
    if isinstance(level, int):
        return level
    
    level_upper = level.upper()
    if level_upper == 'DEBUG':
        return logging.DEBUG
    elif level_upper == 'INFO':
        return logging.INFO
    elif level_upper == 'WARNING' or level_upper == 'WARN':
        return logging.WARNING
    elif level_upper == 'ERROR':
        return logging.ERROR
    elif level_upper == 'CRITICAL':
        return logging.CRITICAL
    else:
        # Default to INFO if unknown
        return logging.INFO


def log_function_call(func: F) -> F:
    """
    Decorator to log function calls.
    
    Args:
        func: Function to decorate
    
    Returns:
        Callable: Decorated function
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        logger = get_logger(func.__module__)
        func_name = func.__name__  # Changed from __qualname__ to __name__
        
        # Log function call with the expected format
        logger.debug(f"Calling {func_name} with args={args}, kwargs={kwargs}")
        
        start_time = datetime.now()
        try:
            result = func(*args, **kwargs)
            end_time = datetime.now()
            duration = end_time - start_time
            
            # Log successful completion
            logger.debug(f"{func_name} completed in {duration.total_seconds():.4f} seconds")
            return result
        except Exception as e:
            end_time = datetime.now()
            duration = end_time - start_time
            
            # Log exception
            logger.error(
                f"{func_name} failed after {duration.total_seconds():.4f} seconds "
                f"with exception: {str(e)}"
            )
            raise
    
    return cast(F, wrapper)


def log_exception(
    logger: logging.Logger,
    exception: Exception,
    context: Optional[Dict[str, Any]] = None,
    level: int = logging.ERROR
) -> None:
    """
    Log an exception with context information.
    
    Args:
        logger: Logger to use
        exception: Exception to log
        context: Additional context information
        level: Log level to use
    """
    exc_type, exc_value, exc_traceback = sys.exc_info()
    
    # Format traceback
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    tb_text = ''.join(tb_lines)
    
    # Basic message
    message = f"Exception: {exception.__class__.__name__}: {str(exception)}"
    
    # Add context if provided
    if context:
        context_str = ', '.join(f"{k}={v}" for k, v in context.items())
        message += f"\nContext: {context_str}"
    
    # Add traceback
    message += f"\nTraceback:\n{tb_text}"
    
    # Log the message
    logger.log(level, message)


def log_progress(
    logger: logging.Logger,
    current: int,
    total: int,
    message: str,
    interval: int = 10,
    level: int = logging.INFO
) -> None:
    """
    Log progress of a long-running operation.
    
    Logs are emitted at regular percentage intervals to avoid log spam.
    
    Args:
        logger: Logger to use
        current: Current progress
        total: Total work to be done
        message: Message template (will be formatted with current, total, and percentage)
        interval: Percentage interval for logging
        level: Log level to use
    """
    if total <= 0:
        return
    
    # Calculate percentage
    percentage = (current * 100) // total
    
    # Log at specified intervals or at 100%
    if percentage % interval == 0 or current == total:
        formatted_message = message.format(
            current=current,
            total=total,
            percentage=percentage
        )
        logger.log(level, formatted_message)


# Initialize root logger with no file by default
root_logger = setup_logging()
