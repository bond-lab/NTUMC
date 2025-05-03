import argparse
import logging
import sys
import os

# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)))

from ntumc.db.wordnet_db import WordNetManager
from ntumc.db.corpus import Corpus

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
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output for detailed logging")
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
def initialize_databases(db_path, wn_db_path):
    corpus = Corpus(db_path)
    wn_manager = WordNetManager(wn_db_path)
    wn_manager.connect()
    return corpus, wn_manager

def process_concept(concept, context, wn_manager, args):
    lemma = concept['clemma']
    meanings = {}
    senses = wn_manager.Senses(lang='eng', lemma=lemma)

    synsets = [synset for _, synset in senses]
    lemmas_dict = wn_manager.Lemmas(synsets, 'eng')

    definitions_dict = wn_manager.get_definitions(synsets, 'eng')

    for synset, definitions in definitions_dict.items():
        senses = ', '.join(lemmas_dict.get(synset, []))
        for definition in definitions:
            meanings[synset] = f"[{senses}] {definition}"

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

    return lemma, meanings

def construct_prompt(context, lemma, meanings):
    return f"""Given the context:

> {context}

Identify the correct tag for _{lemma}_ from these options:

{meanings}

Return only the tag's key."""

def handle_response(prompt, model_name, meanings, dry_run):
    thinking, cleaned_response = generate_and_extract(prompt, model=model_name)
    if thinking is not None:
        logger.info(f"Model thinking: {thinking}")
    logger.info(f"Model response: {cleaned_response}")

    selected_key = cleaned_response.strip()
    if selected_key in meanings:
        selected_value = meanings[selected_key]
    else:
        selected_key = None
        selected_value = None

    if dry_run:
        print("DRY RUN:")
        print(prompt)
        print(f"Selected key: {selected_key}")
        if selected_key:
            print(f"Selected value: {selected_value}")
        print(f"Model response: {cleaned_response}")

def main():
    args = parse_arguments()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    corpus, wn_manager = initialize_databases(args.database, args.wordnet_db)

    from_sid, to_sid = map(int, args.range.split(':'))
    sentences = corpus.get_sentences(from_sid, to_sid)

    for sentence in sentences:
        context = sentence['text']
        for concept in sentence['concepts']:
            lemma, meanings = process_concept(concept, context, wn_manager, args)
            prompt = construct_prompt(context, lemma, meanings)
            handle_response(prompt, args.model, meanings, args.dry_run)

    wn_manager.close()

if __name__ == "__main__":
    main()
