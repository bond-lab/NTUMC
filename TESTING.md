# Testing the NTUMC WordNet Tagger

This document describes how to run tests for the NTUMC WordNet Tagger system.

## Running All Tests

To run all tests:

```
pip install -e .
pytest ntumc/tests/ntumc/tests
```


# To run tests for specific components:

## Language mappings
```
python -m unittest ntumc/tests/config/test_language_mappings.py
```

## Logging system
```
python -m unittest ntumc/tests/core/test_logging.py
```

# Test Coverage
To check test coverage (requires the coverage package):

## Install coverage if not already installed
```
pip install coverage
```

## Run tests with coverage
```
coverage run -m unittest discover -s ntumc/tests
```

## Generate coverage report
```
coverage report -m
```

#Continuous Integration

When I set up CI, add information about how the automated tests are run.

#Writing New Tests

When adding new functionality, please follow these guidelines for writing tests:

1. Place tests in the appropriate subdirectory under ntumc/tests/
2. Name test files with the prefix test_
3. Use descriptive test method names that explain what is being tested
4. Include docstrings for test classes and methods
5. Test both normal operation and edge cases 

