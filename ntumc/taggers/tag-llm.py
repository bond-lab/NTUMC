import argparse
import logging
import sys
import os
from typing import List, Dict, Any, Optional

# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)))

from ntumc.db.wordnet_db import WordNetManager
from ntumc.db.corpus import Corpus

import json
import re
import ollama
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
    parser.add_argument("--context", type=int, default=2, help="Number of sentences before and after to include in context (default: 2)")
    parser.add_argument("--fallback", default="eng", help="Fallback language for definitions/examples when not found in corpus language (default: eng)")
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

def process_concept(concept, context, wn_manager, args, lang='eng', fallback='eng'):
    lemma = concept['clemma']
    meanings = {}
    senses = wn_manager.Senses(lang=lang, lemma=lemma)

    synsets = [synset for _, synset in senses]
    lemmas_dict = wn_manager.Lemmas(synsets, lang)

    definitions_dict = wn_manager.get_definitions(synsets, lang)
    examples_dict = wn_manager.get_examples(synsets, lang)

    use_fallback = fallback != lang
    fallback_defs, fallback_examples = {}, {}
    if use_fallback:
        missing_defs = [s for s in synsets if s not in definitions_dict]
        if missing_defs:
            fallback_defs = wn_manager.get_definitions(missing_defs, fallback)
        missing_ex = [s for s in synsets if s not in examples_dict]
        if missing_ex:
            fallback_examples = wn_manager.get_examples(missing_ex, fallback)

    for synset in synsets:
        senses_str = ', '.join(lemmas_dict.get(synset, []))
        defs = definitions_dict.get(synset)
        is_fb_def = defs is None
        defs = defs or fallback_defs.get(synset, [])
        for definition in defs:
            examples = examples_dict.get(synset, [])
            is_fb_ex = not examples
            if is_fb_ex:
                examples = fallback_examples.get(synset, [])
            def_str = f"{definition} [{fallback}]" if is_fb_def else definition
            ex_str = (
                f" ({'; '.join(examples)} [{fallback}])" if (examples and is_fb_ex)
                else (f" ({'; '.join(examples)})" if examples else "")
            )
            meanings[synset] = f"[{senses_str}] {def_str}{ex_str}"

    if not args.wn_only:
        meanings.update({
            'per': 'name of a person not in wordnet' \
            " (_Irene_ arrived.  Capatin _Vantoch_ laughed.)",
            'org': 'name of an organization not in wordnet' \
            " (I work at _IBM_)",
            'dat': 'date/time that is not in wordnet' \
            " (It starts at _2pm_)",
            'loc': 'name of a place not in wordnet' \
            " (We study in _Olomouc_)",
            'oth': 'other name not in wordnet' \
            " (I use a _Thinkpad_)",
            'year': 'name of a year not in wordnet' \
            " (I was born in _1967_)",
            'num': 'number not in wordnet' \
            " (There were _42_ of them)",
            'e': 'the word was not tokenized or lemmatized correctly' \
            " ('I saw three _does_' lemmatized as _do_ not _doe_)",
            'w': 'wordnet does not have the correct sense' \
            " ('I program in _python_' meaning 'the computer language')",
            'x': 'this is a closed class word (preposition, dummy it/there, relative pronoun, passive or progressive be/have, punctuation, love catlove youloveloa...).   Or it is part of a multiword expression or it is an inappropriate multiword expression.' \
            " ( 'Kim scored a _hat_ trick' _hat_ should be part of _hat trick_)"
        })

    return lemma, meanings

def construct_prompt(context, lemma, meanings):
    return f"""Given the context:

> {context}

Identify the correct tag for the lemma, _{lemma}_, from these options:

{meanings}

Return only the tag's key as a plain string."""

def construct_context(index: int, sentences: List[Dict[str, Any]], context: int) -> str:
    """
    Construct a context string around a given index, handling edge cases.
    
    Args:
        index (int): The central index for context extraction.
        sentences (List[Dict[str, Any]]): List of sentence dictionaries.
        context (int): Number of sentences to include on each side.
    
    Returns:
        str: Concatenated context sentences, or empty string if no valid context.
    """
    # Determine the start and end indices, ensuring they don't go out of bounds
    start_index = max(0, index - context)
    end_index = min(len(sentences), index + context + 1)
    
    # Extract context sentences
    context_sentences = [
        sentence['text'] 
        for sentence in sentences[start_index:end_index]
    ]
    
    # Join and return the context
    return ' '.join(context_sentences)

def extract_key(response: str, meanings: dict) -> Optional[str]:
    """Extract a valid meanings key from a model response string."""
    cleaned = response.strip().strip("'\"")
    if cleaned in meanings:
        return cleaned
    synset_match = re.search(r'\b(\d{8}-[nvra])\b', response)
    if synset_match and synset_match.group(1) in meanings:
        return synset_match.group(1)
    for key in meanings:
        if re.search(rf"'?{re.escape(key)}'?", response):
            return key
    return None


def disambiguate(context, lemma, meanings, model_name):
    prompt = construct_prompt(context, lemma, meanings)
    logger.debug(f"Prompt: {prompt}")

    schema = {
        "type": "object",
        "properties": {"key": {"type": "string", "enum": list(meanings.keys())}},
        "required": ["key"],
    }
    try:
        result = generate(model=model_name, prompt=prompt, format=schema)
        key = json.loads(result['response']).get('key', '').strip()
        if key in meanings:
            logger.info(f"Model response (structured): {key}")
            return key, meanings[key]
    except Exception as e:
        logger.debug(f"Structured output failed ({e}), falling back to text parsing")

    thinking, cleaned_response = generate_and_extract(prompt, model=model_name)
    if thinking is not None:
        logger.debug(f"Model thinking: {thinking}")
    logger.info(f"Model response: {cleaned_response}")
    selected_key = extract_key(cleaned_response, meanings)
    if selected_key in meanings:
        return selected_key, meanings[selected_key]
    return None, None

def sentimentalize(context, lemma, model_name, gloss=''):
    if gloss:
        gloss =f' ({gloss})'
    sentiment_prompt = f"""Given the context:

> {context}

Select a value for the lexical sentiment for _{lemma}_  {gloss} between -100 and 100.
Most words have no sentiment (0), fantastic =95, good = 64, ok = 34, poor = -34, bad = -64, awful = -95.
Just give the sentiment of the word, don't add the effect of modifiers like _not_ or _very_.

Return just the number."""

    _, sentiment_response = generate_and_extract(sentiment_prompt, model=model_name)
    logger.debug(f"Sentiment prompt: {sentiment_prompt}")
    logger.info(f"Sentiment response: {sentiment_response}")
    try:
        score = float(sentiment_response)
    except:
        score = None
    return score

def ensure_model(model_name: str) -> None:
    """Ensure the model is available locally, pulling it if not."""
    available = {m.model for m in ollama.list().models}
    if model_name not in available:
        logger.info(f"Model '{model_name}' not found locally, pulling...")
        for progress in ollama.pull(model_name, stream=True):
            if progress.status:
                if progress.total:
                    logger.info(f"Pull: {progress.status} {progress.completed or 0}/{progress.total}")
                else:
                    logger.info(f"Pull: {progress.status}")
        logger.info(f"Model '{model_name}' ready.")


def main():
    args = parse_arguments()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    ensure_model(args.model)

    corpus, wn_manager = initialize_databases(args.database, args.wordnet_db)
    lang = corpus.get_lang() or 'eng'
    logger.info(f"Corpus language: {lang}")
    margin = args.context
    
    from_sid, to_sid = map(int, args.range.split(':'))
    sids =  corpus.get_sids(from_sid, to_sid, margin)
    sentences = corpus.get_sentences(min(sids), max(sids))

    for i, sentence in enumerate(sentences):
        ## ignore sentences that are just for context
        if sentence['sid'] < from_sid or sentence['sid'] > to_sid:
            continue 
        context = construct_context(i, sentences, margin)
        for concept in sentence['concepts']:
            lemma, meanings = process_concept(concept, context, wn_manager, args, lang, args.fallback)
            selected_key, selected_value = disambiguate(context, lemma, meanings,
                                                        args.model)
            sentiment = None
            if selected_key not in ['x', 'e', None]:
                sentiment = sentimentalize(context, lemma, args.model, gloss=selected_value)

            if args.dry_run:
                print("DRY RUN:")
                print(f"Context: {context}")
                print(f"Selected key: {selected_key}")
                if selected_key:
                    print(f"Selected value: {selected_value}")
                    if sentiment is not None:
                         print(f"Sentiment: {sentiment}")
            else:
                corpus.update_concept_tag(sentence['sid'], concept['cid'],
                                          selected_key, usr=args.model)
                print('updated concept', selected_key, sentiment )
                if sentiment is not None:
                    print ('updating sentiment', sentiment)
                    corpus.update_sentiment_score(sentence['sid'], concept['cid'],
                                                  sentiment, usr=args.model)

    corpus.commit_and_close()
    wn_manager.close()

if __name__ == "__main__":
    main()
