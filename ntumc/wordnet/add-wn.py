#!/usr/bin/python
#  Copyright 2012 Francis Bond; released under the MIT license
#
#  take a wordnet tab file (synset<TAB>lemma) and add it to a wordnet DB
#  wordnet DB uses the schema of the Japanese wordnet 
#     <http://nlpwww.nict.go.jp/wn-ja/index.en.html>
#
import codecs
import sys
import collections
import re
from ntumc.db.wordnet_db import WordNetManager
from ntumc.core.logging_setup import get_logger

logger = get_logger(__name__)

def main():
    delold = True
    ## get wordnet, lang and DB
    if len(sys.argv) < 5:
        logger.error('You need to give at least four arguments: ' 
                    'wn tab file, lang (ISO), projectname, wn DB, delete old (Y/N) default Y')
        sys.exit(1)

    wnfile = sys.argv[1]
    lang = sys.argv[2]
    projectname = sys.argv[3]
    dbfile = sys.argv[4]
    
    if len(sys.argv) > 5 and sys.argv[5] == 'N':
        delold = False

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
for l in f:
    if l.startswith('#'):  ### discard comments
        continue
    else:
        sense = l.strip().split('\t')
        if (len(sense) == 3):  ### check there are three things: ss, type, thing
            if sense[1].endswith('lemma'):  ### and it is a lemma
                ll = sense[2].strip()
                pos = sense[0][-1]
                wn[ll][pos].add(sense[0])
                mm= re.search(r'(.*)\+(.*)',ll)
                if ll.startswith('-'):
                    wn[ll[1:]][pos].add(sense[0])
                    sys.stderr.write('removed hyphen (%s)\n' % ll)
                elif mm:
                    sys.stderr.write('removed +... (%s)\n' % ll)
                    wn[mm.group(1)][pos].add(sense[0])
        elif (len(sense) == 4):  ### check there are three things: ss, type, id, thing
            if sense[1].endswith(':def'):  ### and it is a definition  
                thislang = sense[1][0:3]
                c.execute("""SELECT synset, lang, def, sid 
                             FROM synset_def WHERE synset = ? AND sid = ? AND lang = ?""",
                          (sense[0], thislang, sense[3]))  ## synset, lang, def, sid
                row = c.fetchone()
                if (row): ### shouldn't I constrain this?
                    c.execute("UPDATE synset_def SET def = ?",  (sense[2],))
                else:
                    c.execute("INSERT INTO synset_def(synset, lang, def, sid) VALUES (?,?,?,?)",
                          (sense[0], thislang, sense[3], sense[2]))
            elif sense[1].endswith(':exe'):  ### and it is an example
                thislang = sense[1][0:3]
                c.execute("""SELECT synset, lang, def, sid FROM synset_ex 
                             WHERE synset = ? AND sid = ? AND lang = ?""",
                          (sense[0], thislang, sense[3]))  
                row = c.fetchone()
                if (row):
                    c.execute("UPDATE synset_ex SET def = ?",  (sense[2],))
                else:
                    c.execute("""INSERT INTO synset_ex(synset, lang, def, sid) 
                                 VALUES (?,?,?,?)""",
                              (sense[0], thislang, sense[3], sense[2]))
            # elif sense[1].endswith(':exe'):  ### and it is an example  
            #     lang = sense[1][0:3]
            #     c.execute("INSERT INTO synset_ex VALUES (?,?,?,?)",
            #               (sense[0], lang, sense[3], sense[2]))



for word in wn:
    for pos in wn[word]:
        ## assume one word entry per pos
        c.execute("INSERT INTO word(wordid, lang, lemma, pron, pos) VALUES (?,?,?,?,?)",
                  (None, lang, word, None, pos))
        ## get the id of the word 
        wid = c.lastrowid
        for synset in wn[word][pos]:
            c.execute("""INSERT INTO sense(synset, wordid, lang, 
                                           rank, lexid, freq, src, confidence) 
                                VALUES (?,?,?,?,?,?,?,?)""",
                      (synset, wid, lang, None, None, None, projectname, 1.0))
con.commit()
con.close()


##
## Let them know we're done
##
sys.stderr.write('Added Wordnet (%s) to the database (%s) for %s\n' % \
                   (wnfile, dbfile, lang))
sys.stderr.write('You should probably re-index word and sense tables.\n')
