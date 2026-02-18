# NTUMC Database Manager

The Database Manager module provides utilities for managing SQLite database connections for both WordNet and corpus databases used in the NTUMC tagger.

## Features

- Context manager protocol for safe resource handling
- Transaction management (begin, commit, rollback)
- Query execution with parameter binding
- Convenience methods for common operations (fetch_one, fetch_all, fetch_dict)
- Database utilities (check connection, create backup, optimize)
- Comprehensive error handling
- Thread-safe operations

## Usage

### Basic Connection

```python
from ntumc.db.db_manager import DatabaseManager

# Connect to a database
with DatabaseManager('path/to/database.db') as db:
    # Execute a query
    cursor = db.execute('SELECT * FROM table WHERE column = ?', ('value',))
    
    # Fetch results
    for row in cursor:
        print(row)
```

### Transaction Management

```python
from ntumc.db.db_manager import DatabaseManager

with DatabaseManager('path/to/database.db') as db:
    # Begin a transaction
    db.begin_transaction()
    
    try:
        # Execute multiple queries as a single transaction
        db.execute("INSERT INTO table (column) VALUES (?)", ('value1',))
        db.execute("UPDATE table SET column = ? WHERE id = ?", ('value2', 1))
        
        # Commit the transaction
        db.commit()
    except Exception as e:
        # Roll back on error
        db.rollback()
        raise
```

### Convenience Methods

```python
from ntumc.db.db_manager import DatabaseManager

with DatabaseManager('path/to/database.db') as db:
    # Fetch a single row
    row = db.fetch_one("SELECT * FROM table WHERE id = ?", (1,))
    
    # Fetch all rows
    rows = db.fetch_all("SELECT * FROM table")
    
    # Fetch as dictionary with key_column
    results = db.fetch_dict("SELECT id, name FROM table", key_column='id')
    # Access: results[1]['name']
```

### Database Utilities

```python
from ntumc.db.db_manager import check_connection, create_backup, optimize_database

# Check if a database exists and is accessible
if check_connection('path/to/database.db'):
    # Create a backup before operations
    backup_path = create_backup('path/to/database.db')
    
    # Optimize a database connection
    with DatabaseManager('path/to/database.db') as db:
        optimize_database(db.conn)
```

## Error Handling

The module provides a hierarchy of custom exceptions:

- `DatabaseError`: Base exception for database-related errors
- `ConnectionError`: Exception for connection-related errors 
- `QueryError`: Exception for query execution errors

These exceptions provide context-rich error messages to help with debugging.

## Thread Safety

While SQLite itself handles concurrent reads well, write operations should be properly managed. The DatabaseManager supports thread safety by allowing each thread to have its own connection, but it's the responsibility of the caller to avoid conflicts by using proper synchronization mechanisms when writing to the database from multiple threads.
