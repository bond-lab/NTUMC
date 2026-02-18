#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Examples showing how to use the DatabaseManager.

This module provides practical examples of using the DatabaseManager
for common operations in the NTUMC tagger.
"""

import os
import logging
from ntumc.db.db_manager import DatabaseManager, create_backup, optimize_database

# Setup logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def example_wordnet_lookup(wordnet_db_path, lemma, lang='eng'):
    """
    Example of looking up a lemma in WordNet.
    
    Args:
        wordnet_db_path: Path to the WordNet database.
        lemma: Lemma to look up.
        lang: Language code (default: 'eng').
    
    Returns:
        List of synsets for the given lemma.
    """
    logger.info(f"Looking up lemma '{lemma}' in language '{lang}'")
    
    try:
        with DatabaseManager(wordnet_db_path) as db:
            # Query for synsets
            synsets = db.fetch_all("""
                SELECT sense.synset, sense.lang
                FROM word 
                JOIN sense ON word.wordid = sense.wordid 
                WHERE word.lemma = ? AND sense.lang = ?
            """, (lemma, lang))
            
            if not synsets:
                logger.info(f"No synsets found for lemma '{lemma}' in language '{lang}'")
                return []
            
            logger.info(f"Found {len(synsets)} synsets for lemma '{lemma}'")
            for synset in synsets:
                logger.info(f"  - {synset['synset']} ({synset['lang']})")
            
            return [s['synset'] for s in synsets]
            
    except Exception as e:
        logger.error(f"Error looking up lemma: {str(e)}")
        return []


def example_corpus_tagging(corpus_db_path, wordnet_db_path, sid, lemma, pos, tag, synset):
    """
    Example of tagging a word in the corpus.
    
    Args:
        corpus_db_path: Path to the corpus database.
        wordnet_db_path: Path to the WordNet database.
        sid: Sentence ID.
        lemma: Lemma to tag.
        pos: Part of speech.
        tag: WordNet POS (n, v, a, r).
        synset: WordNet synset ID.
    
    Returns:
        Boolean indicating success or failure.
    """
    logger.info(f"Tagging lemma '{lemma}' in sentence {sid} with synset {synset}")
    
    # First, create a backup of the corpus database
    backup_path = create_backup(corpus_db_path)
    if not backup_path:
        logger.error("Failed to create backup, aborting tagging operation")
        return False
    
    try:
        # Connect to the corpus database
        with DatabaseManager(corpus_db_path) as corpus_db:
            # Begin transaction
            corpus_db.begin_transaction()
            
            try:
                # Find all instances of the lemma in the sentence
                words = corpus_db.fetch_all("""
                    SELECT wid, word, pos, lemma
                    FROM word
                    WHERE sid = ? AND lemma = ?
                    ORDER BY wid
                """, (sid, lemma))
                
                if not words:
                    logger.warning(f"No words with lemma '{lemma}' found in sentence {sid}")
                    corpus_db.rollback()
                    return False
                
                # Get the next available concept ID for this sentence
                result = corpus_db.fetch_one("""
                    SELECT MAX(cid) as max_cid
                    FROM concept
                    WHERE sid = ?
                """, (sid,))
                
                next_cid = 1 if result['max_cid'] is None else result['max_cid'] + 1
                
                # Insert the concept
                corpus_db.execute("""
                    INSERT INTO concept(sid, cid, clemma, tag, tags)
                    VALUES (?, ?, ?, ?, ?)
                """, (sid, next_cid, lemma, tag, synset))
                
                # Connect the concept to the words
                for word in words:
                    corpus_db.execute("""
                        INSERT INTO cwl(sid, cid, wid)
                        VALUES (?, ?, ?)
                    """, (sid, next_cid, word['wid']))
                
                # Commit the transaction
                corpus_db.commit()
                
                logger.info(f"Successfully tagged {len(words)} instances of '{lemma}' with concept ID {next_cid}")
                return True
                
            except Exception as e:
                # Roll back in case of error
                corpus_db.rollback()
                logger.error(f"Error during tagging: {str(e)}")
                return False
    
    except Exception as e:
        logger.error(f"Error connecting to database: {str(e)}")
        return False


def example_batch_update(corpus_db_path, updates):
    """
    Example of performing batch updates to the corpus.
    
    Args:
        corpus_db_path: Path to the corpus database.
        updates: List of (sid, wid, new_pos, new_lemma) tuples.
    
    Returns:
        Number of rows updated.
    """
    logger.info(f"Performing batch update of {len(updates)} words")
    
    # Create a backup
    backup_path = create_backup(corpus_db_path)
    if not backup_path:
        logger.error("Failed to create backup, aborting batch update")
        return 0
    
    try:
        with DatabaseManager(corpus_db_path) as db:
            # Begin transaction
            db.begin_transaction()
            
            try:
                updated_count = 0
                
                for sid, wid, new_pos, new_lemma in updates:
                    # Update the word
                    db.execute("""
                        UPDATE word
                        SET pos = ?, lemma = ?
                        WHERE sid = ? AND wid = ?
                    """, (new_pos, new_lemma, sid, wid))
                    
                    updated_count += db.cursor.rowcount
                
                # Commit the transaction
                db.commit()
                
                logger.info(f"Successfully updated {updated_count} words")
                return updated_count
                
            except Exception as e:
                # Roll back in case of error
                db.rollback()
                logger.error(f"Error during batch update: {str(e)}")
                return 0
    
    except Exception as e:
        logger.error(f"Error connecting to database: {str(e)}")
        return 0


def example_optimize_databases(db_paths):
    """
    Example of optimizing multiple databases.
    
    Args:
        db_paths: List of database paths.
    
    Returns:
        Dictionary of database paths to optimization results.
    """
    logger.info(f"Optimizing {len(db_paths)} databases")
    
    results = {}
    
    for db_path in db_paths:
        try:
            with DatabaseManager(db_path) as db:
                results[db_path] = optimize_database(db.conn)
                
                if results[db_path]:
                    logger.info(f"Successfully optimized database: {db_path}")
                else:
                    logger.warning(f"Failed to optimize database: {db_path}")
        
        except Exception as e:
            logger.error(f"Error optimizing database {db_path}: {str(e)}")
            results[db_path] = False
    
    return results


def example_query_sentences_with_words(corpus_db_path, lemma_list, lang='eng'):
    """
    Example of finding sentences containing specific lemmas.
    
    Args:
        corpus_db_path: Path to the corpus database.
        lemma_list: List of lemmas to search for.
        lang: Language code.
    
    Returns:
        Dictionary mapping sentence IDs to sentences containing the lemmas.
    """
    logger.info(f"Searching for sentences containing lemmas: {', '.join(lemma_list)}")
    
    try:
        with DatabaseManager(corpus_db_path) as db:
            # Placeholder for lemma parameters
            placeholders = ', '.join(['?'] * len(lemma_list))
            
            query = f"""
                SELECT DISTINCT s.sid, s.sent, d.title, c.language
                FROM sent s
                JOIN word w ON s.sid = w.sid
                JOIN doc d ON s.docID = d.docid
                JOIN corpus c ON d.corpusID = c.corpusID
                WHERE w.lemma IN ({placeholders})
                AND c.language = ?
                ORDER BY s.sid
            """
            
            # Add language parameter at the end
            params = lemma_list + [lang]
            
            sentences = db.fetch_dict(query, params, key_column='sid')
            
            if not sentences:
                logger.info(f"No sentences found containing the specified lemmas")
                return {}
            
            logger.info(f"Found {len(sentences)} sentences containing the specified lemmas")
            return sentences
            
    except Exception as e:
        logger.error(f"Error searching for sentences: {str(e)}")
        return {}


if __name__ == "__main__":
    # Example usage
    WORDNET_DB = "path/to/wordnet.db"
    CORPUS_DB = "path/to/corpus.db"
    
    # Only run if the databases exist
    if os.path.exists(WORDNET_DB) and os.path.exists(CORPUS_DB):
        # Look up synsets
        synsets = example_wordnet_lookup(WORDNET_DB, "run")
        
        # Tag a word
        if synsets:
            example_corpus_tagging(CORPUS_DB, WORDNET_DB, 1, "run", "VB", "v", synsets[0])
        
        # Batch update words
        updates = [
            (1, 1, "DT", "this"),
            (1, 2, "VBZ", "be"),
            (1, 3, "DT", "a")
        ]
        example_batch_update(CORPUS_DB, updates)
        
        # Optimize databases
        example_optimize_databases([WORDNET_DB, CORPUS_DB])
        
        # Find sentences with specific lemmas
        sentences = example_query_sentences_with_words(CORPUS_DB, ["run", "jump"])
        for sid, data in sentences.items():
            print(f"Sentence {sid}: {data['sent']}")
    else:
        print(f"Example databases not found at {WORDNET_DB} and {CORPUS_DB}")
        print("Please update the paths to run the examples")
