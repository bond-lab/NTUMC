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
from ntumc.db.corpus import Corpus

def main():
    parser = argparse.ArgumentParser(description='Dump document JSON from ntumc corpus')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('doc_id', nargs='?', type=int, default=None,
                        help='Document ID to dump (default: 440, or use --doc)')
    group.add_argument('--doc', type=str, default=None,
                        help='Document name to dump (overrides doc_id if given)')
    parser.add_argument('--db', type=str, default='corpus.db',
                        help='Path to the corpus database (default: corpus.db)')
    parser.add_argument('--out', type=str, default=None,
                        help='Output file to write JSON (default: stdout)')
    args = parser.parse_args()
    
    # Create a Corpus instance and call dump_doc_json
    corpus = Corpus(args.db)
    if args.doc is not None:
        doc_id = corpus.get_docid_by_docname(args.doc)
        if doc_id is None:
            print(f"Document with doc='{args.doc}' not found.", file=sys.stderr)
            sys.exit(1)
    else:
        doc_id = args.doc_id if args.doc_id is not None else 440

    result = corpus.dump_doc_json(doc_id, out=args.out)
    if args.out is None:
        print(result)
    else:
        print(f"Wrote JSON to {args.out}")

if __name__ == '__main__':
    main()
