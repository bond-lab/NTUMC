#!/bin/bash

# Check if the virtual environment directory exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate the virtual environment
source venv/bin/activate

# Install the requirements if not already installed
pip install -r requirements-dev.txt

# Run the tests
python -m unittest discover ntumc/tests/db

# Deactivate the virtual environment
deactivate
