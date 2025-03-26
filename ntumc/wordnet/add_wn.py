#!/usr/bin/python
#  Copyright 2012 Francis Bond; released under the MIT license
#
#  take a wordnet tab file (synset<TAB>lemma) and add it to a wordnet DB
#  wordnet DB uses the schema of the Japanese wordnet 
#     <http://nlpwww.nict.go.jp/wn-ja/index.en.html>
#
import argparse
import codecs
import collections
import re
import sys
from ntumc.db.wordnet_db import WordNetManager
from ntumc.core.logging_setup import get_logger

logger = get_logger(__name__)

def main():
    parser = argparse.ArgumentParser(description='Add WordNet data to a database.')
    parser.add_argument('wnfile', help='WordNet tab file')
    parser.add_argument('lang', help='Language (ISO code)')
    parser.add_argument('projectname', help='Project name')
    parser.add_argument('dbfile', help='WordNet database file')
    parser.add_argument('--delete-old', dest='delold', action='store_true', 
                        help='Delete old entries for the language (default: False)')

    args = parser.parse_args()

    wnfile = args.wnfile
    lang = args.lang
    projectname = args.projectname
    dbfile = args.dbfile
    delold = args.delold

    logger.info(f'Adding Wordnet {wnfile} to database {dbfile} for language {lang}')
    
    # Initialize database manager
    wn_manager = WordNetManager(dbfile)
    ##
    ## delete old version for this language
    ##
    if delold:
        logger.info(f'Deleting old entries for "{lang}"')
        wn_manager.delete_language_entries(lang)
    ##
    ## read in and update new entries
    ##
    logger.info(f'Inserting wordnet {wnfile} into database {dbfile} for {lang}')

    # Configure database performance
    wn_manager.connect()
    wn_manager.execute("PRAGMA synchronous = OFF")
    wn_manager.execute("PRAGMA journal_mode = MEMORY")

    wn = collections.defaultdict(lambda: collections.defaultdict(set))
    
    # Open and process the wordnet file
    with codecs.open(wnfile, encoding='utf-8', mode='r') as f:
    with codecs.open(wnfile, encoding='utf-8', mode='r') as f:
        for l in f:
            if l.startswith('#'):  # discard comments
                continue
            sense = l.strip().split('\t')
            if len(sense) == 3:  # check there are three things: ss, type, thing
                if sense[1] == 'lemma':  # and it is a lemma
                    ll = sense[2].strip()
                    pos = sense[0][-1]
                    wn[ll][pos].add(sense[0])
                    mm = re.search(r'(.*)\+(.*)', ll)
                    if ll.startswith('-'):
                        wn[ll[1:]][pos].add(sense[0])
                        sys.stderr.write('removed hyphen (%s)\n' % ll)
                    elif mm:
                        sys.stderr.write('removed +... (%s)\n' % ll)
                        wn[mm.group(1)][pos].add(sense[0])
            elif len(sense) == 4:  # check there are four things: ss, type, id, thing
                if sense[1].endswith(':def'):  # and it is a definition
                    thislang = sense[1][0:3]
                    wn_manager.update_synset_def(
                        synset=sense[0],
                        lang=thislang,
                        definition=sense[2],
                        sid=sense[3]
                    )
                elif sense[1].endswith(':exe'):  # and it is an example
                    thislang = sense[1][0:3]
                    wn_manager.update_synset_ex(
                        synset=sense[0],
                        lang=thislang,
                        example=sense[2],
                        sid=sense[3]
                    )
            # elif sense[1].endswith(':exe'):  ### and it is an example  
            #     lang = sense[1][0:3]
            #     c.execute("INSERT INTO synset_ex VALUES (?,?,?,?)",
            #               (sense[0], lang, sense[3], sense[2]))



    # Process all words and synsets
    for word in wn:
        for pos in wn[word]:
            # Insert word and get wordid
            wordid = wn_manager.insert_word(lang=lang, word=word, pos=pos)
            
            # Insert all senses for this word
            for synset in wn[word][pos]:
                wn_manager.insert_sense(
                    synset=synset,
                    wordid=wordid,
                    lang=lang,
                    projectname=projectname
                )
    
    # Final cleanup
    wn_manager.close()


##
## Let them know we're done
##
    logger.info('Added Wordnet (%s) to the database (%s) for %s', wnfile, dbfile, lang)
    logger.info('You should probably re-index word and sense tables.')

if __name__ == "__main__":
    main()
