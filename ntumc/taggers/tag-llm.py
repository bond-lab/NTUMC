import argparse
import logging
import sys
import os

# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)))

from ntumc.db.wordnet_db import WordNetManager

from ollama import chat, ChatResponse

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


    # Example: Retrieve context and meanings from the database
    # This is a placeholder for actual database queries
    context = "A sea captain or something. They said he’d been out looking for pearls. Mister Golombek looked at Mister Valenta."
    meanings = {
        '13901585-n': '{drop, bead, pearl} a shape that is spherical and small',
        '13372403-n': '{pearl} a smooth lustrous round structure inside the shell of a clam or oyster; much valued as a jewel',
        '01383800-v': '{pearl} gather pearls, from oysters in the ocean',
        '80000204-n': '{pearl} a person or thing that is beautiful, brilliant or valuable, like a pearl',
        '04961331-n': '{ivory, pearl, bone, off-white, pearl-white} a shade of white the color of bleached bones'
    }

    # Construct the prompt
    prompt = f"Which meaning of the word _pearl_ is expressed in the following context:\n\n{context}\n\nThe meanings are as follows:\n{meanings}"

    # Get the response from the language model
    response: ChatResponse = chat(model=model_name, messages=[
        {
            'role': 'user',
            'content': prompt,
        },
    ])
    logger.info(f"Model response: {response.message.content}")

    # If dry-run, print the response
    if dry_run:
        print(f"Dry run: Selected meaning key is {response.message.content}")

    # If dry-run, print a placeholder message
    if dry_run:
        print("Dry run: tagging logic would be executed here.")

    # Close the database connection
    wn_manager.close()

if __name__ == "__main__":
    main()
