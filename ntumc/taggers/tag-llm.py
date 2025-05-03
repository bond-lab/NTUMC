import argparse
import logging
import sys
import os

# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)))

from ntumc.db.wordnet_db import WordNetManager

import re
from ollama import chat, ChatResponse, generate

# Initialize logger
logger = logging.getLogger(__name__)

def parse_arguments():
    parser = argparse.ArgumentParser(description="Tag a span in the specified NTUMC database using a language model.")
    parser.add_argument("range", help="The range of text to tag, in the format from:to")
    parser.add_argument("database", help="Path to the NTUMC database file")
    parser.add_argument("wordnet_db", help="Path to the WordNet database file")
    parser.add_argument("--dry-run", action="store_true", help="Print the selected tags to standard output without making changes")
    parser.add_argument("-m", "--model", default="qwen3:8b", help="Specify the model to use (default: qwen3:8b)")
    parser.add_argument("--wn-only", action="store_true", help="Use only WordNet meanings, exclude additional tags")
    return parser.parse_args()

def generate_and_extract(prompt, model='llama3'):
    result = generate(model=model, prompt=prompt)
    response = result['response']

    # Extract content within <think></think>
    think_match = re.search(r'<think>(.*?)</think>', response, re.DOTALL)
    
    if think_match:
        thinking = think_match.group(1).strip()
        # Remove the thinking part from the main response
        cleaned_response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
    else:
        thinking = None
        cleaned_response = response.strip()

    return thinking, cleaned_response
def main():
    args = parse_arguments()
    db_path = args.database
    wn_db_path = args.wordnet_db
    text_range = args.range
    dry_run = args.dry_run
    model_name = args.model

    # Connect to the WordNet database
    wn_manager = WordNetManager(wn_db_path)
    wn_manager.connect()


    # Retrieve meanings and definitions from WordNet
    lemma = 'look'  # This should be dynamically set based on input
    meanings = {}
    senses = wn_manager.Senses(lang='eng', lemma=lemma)

    synsets = [synset for _, synset in senses]
    lemmas_dict = wn_manager.Lemmas(synsets, 'eng')

    definitions_dict = wn_manager.get_definitions(synsets, 'eng')

    for synset, definitions in definitions_dict.items():
        senses = ', '.join(lemmas_dict.get(synset, []))
        for definition in definitions:
            meanings[synset] = f"[{senses}] {definition}"

    # Example context
    context = "A sea captain or something. They said he’d been out looking for pearls. Mister Golombek looked at Mister Valenta."
    # Add additional tags if --wn-only is not specified
    if not args.wn_only:
        meanings.update({
            'per': 'name of a person not in wordnet',
            'org': 'name of an organization not in wordnet',
            'dat': 'date/time that is not in wordnet',
            'loc': 'name of a place not in wordnet',
            'oth': 'other name not in wordnet',
            'year': 'name of a year not in wordnet',
            'e': 'the word was not tokenized or lemmatized correctly',
            'w': 'wordnet does not have the correct sense',
            'x': 'this is a closed class word or part of a multiword expression'
        })

    # Construct the prompt
    prompt = f"""Given the context:

> {context}

Identify the correct tag for _{lemma}_ from these options:

{meanings}

Return only the tag's key."""

    # Get the response from the language model
    thinking, cleaned_response = generate_and_extract(prompt, model=model_name)
    logger.info(f"Model thinking: {thinking}")
    logger.info(f"Model response: {cleaned_response}")

    # Check if the response is a key in meanings
    selected_key = cleaned_response.strip()
    if selected_key in meanings:
        selected_value = meanings[selected_key]
    else:
        selected_key = None
        selected_value = None

    # If dry-run, print the prompt and response
    if dry_run:
        print("DRY RUN:")
        print(prompt)
        print(f"Selected key: {selected_key}")
        if selected_key:
            print(f"Selected value: {selected_value}")
        print(f"Model response: {cleaned_response}")

    # Close the database connection
    wn_manager.close()

if __name__ == "__main__":
    main()
