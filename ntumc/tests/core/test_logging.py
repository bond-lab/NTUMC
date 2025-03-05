"""
Unit tests for the logging system.

This module tests the logging configuration and utilities.
"""
import os
import unittest
import logging
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from ntumc.core.logging_setup import (
    setup_logging,
    get_logger,
    get_log_level,
    log_function_call,
    log_exception,
    log_progress
)


class TestLoggingSetup(unittest.TestCase):
    """Test the logging setup functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create a temporary directory for log files
        self.test_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.test_dir, 'test.log')
    
    def tearDown(self):
        """Clean up test fixtures."""
        # Remove temporary directory and its contents
        shutil.rmtree(self.test_dir)
        
        # Reset the root logger
        logger = logging.getLogger('ntumc')
        for handler in logger.handlers:
            if isinstance(handler, logging.FileHandler):
                handler.close()
        logger.handlers.clear()
    
    def test_default_setup(self):
        """Test setup with default configuration."""
        logger = setup_logging()
        
        self.assertEqual(logger.name, 'ntumc')
        self.assertEqual(logger.level, logging.INFO)
        self.assertEqual(len(logger.handlers), 1)  # Console handler only
        self.assertFalse(logger.propagate)
    
    def test_custom_setup(self):
        """Test setup with custom configuration."""
        config = {
            'log_level': 'DEBUG',
            'log_file': self.log_file,
            'console_log_level': 'WARNING',
            'file_log_level': 'INFO',
            'max_file_size': 1024,
            'backup_count': 3,
            'propagate': True
        }
        
        logger = setup_logging(config)
        
        self.assertEqual(logger.name, 'ntumc')
        self.assertEqual(logger.level, logging.DEBUG)
        self.assertEqual(len(logger.handlers), 2)  # Console and file handlers
        self.assertTrue(logger.propagate)
        
        # Check console handler
        console_handler = logger.handlers[0]
        self.assertEqual(console_handler.level, logging.WARNING)
        
        # Check file handler
        file_handler = logger.handlers[1]
        self.assertEqual(file_handler.level, logging.INFO)
        self.assertEqual(file_handler.baseFilename, self.log_file)
    
    def test_log_file_creation(self):
        """Test that log files are created as needed."""
        nested_path = os.path.join(self.test_dir, 'logs', 'nested', 'test.log')
        
        config = {
            'log_file': nested_path
        }
        
        logger = setup_logging(config)
        
        # Directory should be created
        self.assertTrue(os.path.exists(os.path.dirname(nested_path)))
        
        # Log something to create the file
        logger.info("Test message")
        
        # Log file should exist
        self.assertTrue(os.path.exists(nested_path))
    
    def test_get_logger(self):
        """Test getting a module-specific logger."""
        # Set up the root logger first
        setup_logging()
        
        # Get a module logger
        module_logger = get_logger('test_module')
        
        self.assertEqual(module_logger.name, 'ntumc.test_module')
    
    def test_get_log_level(self):
        """Test converting log level names to numeric values."""
        self.assertEqual(get_log_level('DEBUG'), logging.DEBUG)
        self.assertEqual(get_log_level('INFO'), logging.INFO)
        self.assertEqual(get_log_level('WARNING'), logging.WARNING)
        self.assertEqual(get_log_level('WARN'), logging.WARNING)
        self.assertEqual(get_log_level('ERROR'), logging.ERROR)
        self.assertEqual(get_log_level('CRITICAL'), logging.CRITICAL)
        
        # Test unknown level (should default to INFO)
        self.assertEqual(get_log_level('UNKNOWN'), logging.INFO)
        
        # Test numeric level
        self.assertEqual(get_log_level(logging.DEBUG), logging.DEBUG)
    
    def test_unicode_logging(self):
        """Test logging Unicode text."""
        config = {
            'log_file': self.log_file
        }
        
        logger = setup_logging(config)
        
        # Log Unicode text
        unicode_text = "Unicode test: 你好，世界！ こんにちは、世界！ Привет, мир!"
        logger.info(unicode_text)
        
        # Check log file
        with open(self.log_file, 'r', encoding='utf-8') as f:
            log_content = f.read()
            self.assertIn(unicode_text, log_content)


class TestLoggingDecorators(unittest.TestCase):
    """Test the logging decorators and utilities."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create a mock logger
        self.mock_logger = MagicMock(spec=logging.Logger)
        
        # Patch get_logger to return our mock
        self.get_logger_patcher = patch('ntumc.core.logging_setup.get_logger', return_value=self.mock_logger)
        self.mock_get_logger = self.get_logger_patcher.start()
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.get_logger_patcher.stop()
    
    def test_log_function_call(self):
        """Test the function call logging decorator."""
        # Define a test function with the decorator
        @log_function_call
        def test_function(a, b, c=None):
            if c is None:
                return a + b
            return a + b + c
        
        # Call the function
        result = test_function(1, 2, c=3)
        
        # Check the result
        self.assertEqual(result, 6)
        
        # Verify debug logs were made
        self.assertEqual(self.mock_logger.debug.call_count, 2)
        
        # Get the debug message from the mock
        first_call_args = self.mock_logger.debug.call_args_list[0][0][0]
        second_call_args = self.mock_logger.debug.call_args_list[1][0][0]
        
        # Check log messages
        self.assertIn("Calling test_function", first_call_args)
        self.assertIn("args=(1, 2)", first_call_args)
        self.assertIn("kwargs={'c': 3}", first_call_args)
        self.assertIn("test_function completed", second_call_args)
    
    def test_log_function_call_exception(self):
        """Test the function call logging decorator with an exception."""
        # Define a test function with the decorator
        @log_function_call
        def test_function():
            raise ValueError("Test error")
        
        # Call the function (should raise)
        with self.assertRaises(ValueError):
            test_function()
        
        # Verify logs were made
        self.assertEqual(self.mock_logger.debug.call_count, 1)
        self.assertEqual(self.mock_logger.error.call_count, 1)
        
        # Get the debug and error messages from the mock
        debug_message = self.mock_logger.debug.call_args_list[0][0][0]
        error_message = self.mock_logger.error.call_args_list[0][0][0]
        
        # Check log messages
        self.assertIn("Calling test_function", debug_message)
        self.assertIn("test_function failed", error_message)
        self.assertIn("Test error", error_message)
    
    def test_log_exception(self):
        """Test logging exceptions with context."""
        logger = MagicMock(spec=logging.Logger)
        
        try:
            # Raise an exception
            raise ValueError("Test error")
        except Exception as e:
            # Log it
            context = {"param1": "value1", "param2": 42}
            log_exception(logger, e, context)
        
        # Verify the log was made
        logger.log.assert_called_once()
        
        # Get the log message from the mock
        log_message = logger.log.call_args[0][1]
        
        # Check log message
        self.assertIn("Exception: ValueError: Test error", log_message)
        self.assertIn("Context: ", log_message)
        self.assertIn("param1=value1", log_message)
        self.assertIn("param2=42", log_message)
        self.assertIn("Traceback:", log_message)
    
    def test_log_progress(self):
        """Test logging progress at intervals."""
        logger = MagicMock(spec=logging.Logger)
        
        # Log progress at 10% intervals
        for i in range(0, 101, 5):
            log_progress(
                logger, i, 100,
                "Progress: {current}/{total} ({percentage}%)",
                interval=10
            )
        
        # Should log at 0%, 10%, 20%, ..., 100%
        self.assertEqual(logger.log.call_count, 11)
        
        # Check the log messages
        for i, call in enumerate(logger.log.call_args_list):
            # Extract the message
            message = call[0][1]
            expected_percentage = i * 10
            self.assertIn(f"({expected_percentage}%)", message)


if __name__ == '__main__':
    unittest.main()
