import argparse
import logging
import sys
import os

# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)))

from ntumc.db.wordnet_db import WordNetManager
from uv import UVClient

# Initialize logger
logger = logging.getLogger(__name__)

def parse_arguments():
    parser = argparse.ArgumentParser(description="Tag a span in the specified NTUMC database using a language model.")
    parser.add_argument("range", help="The range of text to tag, in the format from:to")
    parser.add_argument("database", help="Path to the NTUMC database file")
    parser.add_argument("--dry-run", action="store_true", help="Print the selected tags to standard output without making changes")
    parser.add_argument("-m", "--model", default="qwen3:8b", help="Specify the model to use (default: qwen3:8b)")
    return parser.parse_args()

def main():
    args = parse_arguments()
    db_path = args.database
    text_range = args.range
    dry_run = args.dry_run
    model_name = args.model

    # Connect to the WordNet database
    wn_manager = WordNetManager(db_path)
    wn_manager.connect()

    # Initialize UV client
    client = UVClient(model=model_name)

    # Example of how to use the client to get a response
    # This is a placeholder for the actual tagging logic
    response = client.generate("Example prompt")
    logger.info(f"Model response: {response}")

    # If dry-run, print the response
    if dry_run:
        print(response)

    # Close the database connection
    wn_manager.close()

if __name__ == "__main__":
    main()
