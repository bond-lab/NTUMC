#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database Manager for NTUMC Tagger.

This module provides utilities for managing SQLite database connections
for both WordNet and corpus databases used in the NTUMC tagger.
"""

import os
import sqlite3
import logging
import shutil
from typing import Optional, Union, List, Dict, Any, Tuple, Callable
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# Setup logger
logger = logging.getLogger(__name__)

class DatabaseError(Exception):
    """Base exception for database-related errors."""
    pass

class ConnectionError(DatabaseError):
    """Exception raised for connection-related errors."""
    pass

class QueryError(DatabaseError):
    """Exception raised for query execution errors."""
    pass

class DatabaseManager:
    """
    Manager for SQLite database connections.
    
    This class handles connection creation, cleanup, and transaction management
    for SQLite databases used in the NTUMC tagger. It implements the context
    manager protocol for safe resource handling.
    
    Attributes:
        db_path (str): Path to the SQLite database file.
        conn (sqlite3.Connection): SQLite connection object.
        cursor (sqlite3.Cursor): SQLite cursor object.
        autocommit (bool): Whether to automatically commit after each execution.
        in_transaction (bool): Whether a transaction is currently active.
    """
    
    def __init__(self, db_path: Union[str, Path], autocommit: bool = False, 
                 pragmas: Optional[Dict[str, Any]] = None,
                 check_foreign_keys: bool = True,
                 row_factory: Optional[Callable] = None):
        """
        Initialize a new database manager.
        
        Args:
            db_path: Path to the SQLite database file.
            autocommit: Whether to automatically commit after each execution.
            pragmas: Dictionary of PRAGMA settings to apply on connection.
            check_foreign_keys: Whether to enable foreign key constraints.
            row_factory: Custom row factory for the connection.
        
        Raises:
            ConnectionError: If the database file doesn't exist or can't be accessed.
        """
        self.db_path = str(db_path)
        self.autocommit = autocommit
        self.pragmas = pragmas or {}
        self.check_foreign_keys = check_foreign_keys
        self.row_factory = row_factory or sqlite3.Row
        self.conn = None
        self.cursor = None
        self.in_transaction = False
        
        # Validate database file existence
        if not check_connection(self.db_path):
            raise ConnectionError(f"Database file not found or not accessible: {self.db_path}")
    
    def __enter__(self) -> 'DatabaseManager':
        """
        Enter the context manager, establishing the database connection.
        
        Returns:
            Self, allowing for method chaining.
            
        Raises:
            ConnectionError: If the connection cannot be established.
        """
        try:
            self.connect()
            return self
        except Exception as e:
            raise ConnectionError(f"Failed to establish database connection: {str(e)}") from e
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """
        Exit the context manager, closing the database connection.
        
        Args:
            exc_type: Exception type if an exception was raised.
            exc_val: Exception value if an exception was raised.
            exc_tb: Exception traceback if an exception was raised.
            
        Returns:
            Boolean indicating whether any exception was handled.
        """
        if exc_type is not None:
            logger.error(f"Exception occurred in database context: {exc_type.__name__}: {exc_val}")
            self.rollback()
        else:
            if self.in_transaction:
                self.commit()
        
        self.close()
        return False  # Let the exception propagate
    
    def connect(self) -> None:
        """
        Establish a connection to the database.
        
        Raises:
            ConnectionError: If the connection cannot be established.
        """
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = self.row_factory
            
            # Apply pragmas
            if self.check_foreign_keys:
                self.conn.execute("PRAGMA foreign_keys = ON")
            
            for key, value in self.pragmas.items():
                self.conn.execute(f"PRAGMA {key} = {value}")
            
            self.cursor = self.conn.cursor()
            logger.debug(f"Connected to database: {self.db_path}")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to database: {str(e)}") from e
    
    def close(self) -> None:
        """Close the database connection."""
        if self.conn:
            try:
                self.conn.close()
                logger.debug(f"Closed connection to database: {self.db_path}")
            except Exception as e:
                logger.error(f"Error closing database connection: {str(e)}")
            finally:
                self.conn = None
                self.cursor = None
                self.in_transaction = False
    
    def begin_transaction(self) -> None:
        """
        Begin a new transaction.
        
        Raises:
            DatabaseError: If a transaction is already active.
        """
        if self.in_transaction:
            raise DatabaseError("Transaction already in progress")
        
        if not self.conn:
            self.connect()
        
        self.conn.execute("BEGIN TRANSACTION")
        self.in_transaction = True
        logger.debug("Transaction started")
    
    def commit(self) -> None:
        """
        Commit the current transaction.
        
        Raises:
            DatabaseError: If no transaction is active.
        """
        if not self.in_transaction:
            raise DatabaseError("No transaction in progress to commit")
        
        if not self.conn:
            raise ConnectionError("No active connection to commit")
        
        try:
            self.conn.commit()
            self.in_transaction = False
            logger.debug("Transaction committed")
        except Exception as e:
            raise DatabaseError(f"Failed to commit transaction: {str(e)}") from e
    
    def rollback(self) -> None:
        """
        Roll back the current transaction.
        
        This method is safe to call even if no transaction is active.
        """
        if not self.conn:
            logger.warning("No active connection to rollback")
            return
        
        try:
            self.conn.rollback()
            self.in_transaction = False
            logger.debug("Transaction rolled back")
        except Exception as e:
            logger.error(f"Failed to rollback transaction: {str(e)}")
    
    def execute(self, query: str, params: Optional[Union[Tuple, Dict, List]] = None) -> sqlite3.Cursor:
        """
        Execute a SQL query with optional parameters.
        
        Args:
            query: SQL query to execute.
            params: Parameters to bind to the query.
            
        Returns:
            SQLite cursor after query execution.
            
        Raises:
            QueryError: If the query execution fails.
        """
        if not self.conn:
            self.connect()
        
        try:
            if params is None:
                self.cursor.execute(query)
            else:
                self.cursor.execute(query, params)
            
            if self.autocommit and not self.in_transaction:
                self.conn.commit()
            
            return self.cursor
        except Exception as e:
            if self.autocommit and not self.in_transaction:
                self.conn.rollback()
            raise QueryError(f"Query execution failed: {str(e)}\nQuery: {query}\nParams: {params}") from e
    
    def executemany(self, query: str, params_list: List[Union[Tuple, Dict]]) -> sqlite3.Cursor:
        """
        Execute a SQL query with multiple sets of parameters.
        
        Args:
            query: SQL query to execute.
            params_list: List of parameter sets to bind to the query.
            
        Returns:
            SQLite cursor after query execution.
            
        Raises:
            QueryError: If the query execution fails.
        """
        if not self.conn:
            self.connect()
        
        try:
            self.cursor.executemany(query, params_list)
            
            if self.autocommit and not self.in_transaction:
                self.conn.commit()
            
            return self.cursor
        except Exception as e:
            if self.autocommit and not self.in_transaction:
                self.conn.rollback()
            raise QueryError(f"Query execution failed: {str(e)}\nQuery: {query}") from e
    
    def executescript(self, script: str) -> sqlite3.Cursor:
        """
        Execute a SQL script.
        
        Args:
            script: SQL script to execute.
            
        Returns:
            SQLite cursor after script execution.
            
        Raises:
            QueryError: If the script execution fails.
        """
        if not self.conn:
            self.connect()
        
        try:
            self.cursor.executescript(script)
            
            if self.autocommit and not self.in_transaction:
                self.conn.commit()
            
            return self.cursor
        except Exception as e:
            if self.autocommit and not self.in_transaction:
                self.conn.rollback()
            raise QueryError(f"Script execution failed: {str(e)}\nScript: {script[:100]}...") from e
    
    def fetch_one(self, query: str, params: Optional[Union[Tuple, Dict, List]] = None) -> Optional[sqlite3.Row]:
        """
        Execute a query and fetch a single row result.
        
        Args:
            query: SQL query to execute.
            params: Parameters to bind to the query.
            
        Returns:
            A single row result or None if no results.
            
        Raises:
            QueryError: If the query execution fails.
        """
        cursor = self.execute(query, params)
        return cursor.fetchone()
    
    def fetch_all(self, query: str, params: Optional[Union[Tuple, Dict, List]] = None) -> List[sqlite3.Row]:
        """
        Execute a query and fetch all row results.
        
        Args:
            query: SQL query to execute.
            params: Parameters to bind to the query.
            
        Returns:
            List of all row results.
            
        Raises:
            QueryError: If the query execution fails.
        """
        cursor = self.execute(query, params)
        return cursor.fetchall()
    
    def fetch_dict(self, query: str, params: Optional[Union[Tuple, Dict, List]] = None, 
                  key_column: str = None) -> Union[Dict, List[Dict]]:
        """
        Execute a query and fetch results as a dictionary.
        
        If key_column is provided, returns a dictionary with the key_column values as keys.
        Otherwise, returns a list of dictionaries for each row.
        
        Args:
            query: SQL query to execute.
            params: Parameters to bind to the query.
            key_column: Column to use as dictionary keys.
            
        Returns:
            Dictionary or list of dictionaries with results.
            
        Raises:
            QueryError: If the query execution fails.
            ValueError: If key_column is not in the result set.
        """
        original_row_factory = self.conn.row_factory
        self.conn.row_factory = sqlite3.Row
        
        try:
            cursor = self.execute(query, params)
            results = cursor.fetchall()
            
            if not results:
                return {} if key_column else []
            
            if key_column:
                if key_column not in results[0].keys():
                    raise ValueError(f"Key column '{key_column}' not found in result set")
                
                return {row[key_column]: dict(row) for row in results}
            else:
                return [dict(row) for row in results]
        finally:
            self.conn.row_factory = original_row_factory
    
    def table_exists(self, table_name: str) -> bool:
        """
        Check if a table exists in the database.
        
        Args:
            table_name: Name of the table to check.
            
        Returns:
            Boolean indicating whether the table exists.
        """
        query = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
        result = self.fetch_one(query, (table_name,))
        return result is not None


def check_connection(db_path: Union[str, Path]) -> bool:
    """
    Verify that a database exists and is accessible.
    
    Args:
        db_path: Path to the SQLite database file.
        
    Returns:
        Boolean indicating whether the database is accessible.
    """
    db_path = str(db_path)
    
    if not os.path.exists(db_path):
        logger.error(f"Database file does not exist: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        conn.close()
        return True
    except sqlite3.Error as e:
        logger.error(f"Failed to connect to database: {str(e)}")
        return False


def create_backup(db_path: Union[str, Path], backup_dir: Optional[Union[str, Path]] = None) -> Optional[str]:
    """
    Create a backup of a database before operations.
    
    Args:
        db_path: Path to the SQLite database file.
        backup_dir: Directory to store the backup (defaults to same directory as db_path).
        
    Returns:
        Path to the backup file, or None if backup failed.
    """
    db_path = str(db_path)
    
    if not os.path.exists(db_path):
        logger.error(f"Cannot backup non-existent database: {db_path}")
        return None
    
    try:
        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_name = os.path.basename(db_path)
        backup_name = f"{os.path.splitext(db_name)[0]}_{timestamp}.backup.db"
        
        # Determine backup directory
        if backup_dir:
            backup_dir = str(backup_dir)
            os.makedirs(backup_dir, exist_ok=True)
        else:
            backup_dir = os.path.dirname(db_path)
        
        backup_path = os.path.join(backup_dir, backup_name)
        
        # Create backup using shutil
        shutil.copy2(db_path, backup_path)
        logger.info(f"Created database backup: {backup_path}")
        
        return backup_path
    except Exception as e:
        logger.error(f"Failed to create database backup: {str(e)}")
        return None


def optimize_database(conn: sqlite3.Connection) -> bool:
    """
    Apply PRAGMA optimizations for SQLite.
    
    Args:
        conn: SQLite connection object.
        
    Returns:
        Boolean indicating success or failure.
    """
    try:
        # Common performance-related pragmas
        optimizations = [
            "PRAGMA journal_mode = WAL",
            "PRAGMA synchronous = NORMAL",
            "PRAGMA temp_store = MEMORY",
            "PRAGMA mmap_size = 30000000000",
            "PRAGMA cache_size = -20000",  # Negative means kibibytes
            "PRAGMA foreign_keys = ON"
        ]
        
        for optimization in optimizations:
            conn.execute(optimization)
        
        # Run ANALYZE to optimize query planner
        conn.execute("ANALYZE")
        
        # Vacuum to compact the database
        conn.execute("VACUUM")
        
        conn.commit()
        logger.info("Database optimizations applied successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to optimize database: {str(e)}")
        return False


@contextmanager
def get_connection(db_path: Union[str, Path], **kwargs) -> sqlite3.Connection:
    """
    Context manager for getting a database connection.
    
    Usage:
        with get_connection('path/to/db.sqlite') as conn:
            conn.execute(...)
    
    Args:
        db_path: Path to the SQLite database file.
        **kwargs: Additional arguments for sqlite3.connect.
        
    Yields:
        sqlite3.Connection: Active database connection.
        
    Raises:
        ConnectionError: If connection cannot be established.
    """
    conn = None
    try:
        conn = sqlite3.connect(str(db_path), **kwargs)
        
        # Apply basic pragmas
        conn.execute("PRAGMA foreign_keys = ON")
        
        yield conn
    except sqlite3.Error as e:
        raise ConnectionError(f"Failed to connect to database {db_path}: {str(e)}") from e
    finally:
        if conn:
            conn.close()
