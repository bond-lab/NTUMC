#!/usr/bin/env python
"""
Script to dump document JSON from ntumc corpus.
Usage: python dump_doc.py [DOC_ID]
Default DOC_ID is 440 if none is provided.
"""

import sys
import os
import argparse

# Get the current script's directory
script_dir = os.path.dirname(os.path.abspath(__file__))

# Calculate the project root directory (one level up from scripts)
project_root = os.path.abspath(os.path.join(script_dir, os.pardir))

# Add the project root to the Python path
sys.path.insert(0, project_root)

# Now import from ntumc
from ntumc.db import corpus

def main():
    parser = argparse.ArgumentParser(description='Dump document JSON from ntumc corpus')
    parser.add_argument('doc_id', nargs='?', type=int, default=440, 
                        help='Document ID to dump (default: 440)')
    args = parser.parse_args()
    
    # Call the dump_doc_json function with the provided document ID
    corpus.dump_doc_json(args.doc_id)

if __name__ == '__main__':
    main()
