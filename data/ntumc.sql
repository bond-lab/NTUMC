-- NTU Multilingual Corpus (NTU-MC) schema
-- One database per language (e.g. eng.db, cmn.db, jpn.db).
-- All annotation changes are journaled via *_log tables and triggers.

-- Database-level metadata (one row per database).
CREATE TABLE meta (
       title TEXT       -- human-readable corpus title
       ,license TEXT    -- license identifier or URL
       ,lang TEXT       -- ISO 639-3 language code (e.g. 'eng', 'cmn')
       ,version TEXT    -- schema or data version string
       ,master TEXT     -- master server URL for replication, if any
);

-- A corpus groups related documents by source or genre
-- (e.g. 'yoursing' = Singapore tourism pages, 'story' = short stories).
-- Four core genres: tourism, story, essay, news; plus gloss and semcor.
-- corpusID values are broadly consistent across language databases but
-- not guaranteed identical; the 'corpus' short name is the stable key.
-- Sentence ID ranges partition by genre:
--       1+ = essay (catb), 10000+ = story (danc), 11000+ = story (spec),
--   60000+ = news (kc), 100000+ = tourism (yoursing),
--  110000+ = tourism2 (med), 120000+ = gloss (wngloss),
--  300000+ = semcor.
CREATE TABLE corpus (
       corpusID INTEGER PRIMARY KEY
       ,corpus TEXT      -- short identifier (e.g. 'yoursing', 'story', 'kc')
       ,title TEXT       -- human-readable title, often in the corpus language
       ,language TEXT    -- language code (may duplicate meta.lang)
);

-- A document is a single text (web page, chapter, article) within a corpus.
CREATE TABLE doc (
       docid INTEGER PRIMARY KEY
       ,doc TEXT         -- short machine-readable name (e.g. 'wind-shadow', 'kc01')
       ,title TEXT       -- human-readable title shown in the UI
       ,url TEXT         -- source URL of the original document
       ,subtitle TEXT    -- optional subtitle or description
       ,corpusID INTEGER -- parent corpus
       ,FOREIGN KEY (corpusID) REFERENCES corpus(corpusID)
);

-- A sentence within a document.
-- Sentences are the primary unit of annotation; sid is globally unique
-- across all documents and corpora within a language database.
CREATE TABLE sent (
       sid INTEGER PRIMARY KEY
       ,docID INTEGER   -- parent document
       ,pid TEXT         -- paragraph ID within the document
       ,sent TEXT        -- raw sentence text
       ,comment TEXT     -- annotator comment
       ,usrname TEXT     -- last annotator username
       ,FOREIGN KEY(docID) REFERENCES doc(docID)
);

-- Sentence type / structural markup (heading level, paragraph break, etc.).
-- One row per sentence; stype values include 'h1'...'h7' for headings
-- and 'p' for paragraph starts.
CREATE TABLE stype (
       sid INTEGER
       ,stype TEXT       -- structural type (e.g. 'h1', 'p')
       ,comment TEXT
       ,FOREIGN KEY(sid) REFERENCES sent(sid)
);

-- A word token within a sentence.
-- wid is unique within a sentence (not globally); the true PK is (sid, wid).
CREATE TABLE word (
       sid INTEGER
       ,wid INTEGER      -- word position within the sentence (1-based)
       ,word TEXT         -- surface form as it appears in the text
       ,pos TEXT          -- part-of-speech tag
       ,lemma TEXT        -- lemmatised form
       ,cfrom INTEGER     -- character offset start in sent.sent
       ,cto INTEGER       -- character offset end (exclusive) in sent.sent
       ,comment TEXT
       ,usrname TEXT      -- last annotator username
       ,PRIMARY KEY (sid, wid)
       ,FOREIGN KEY(sid) REFERENCES sent(sid)
);

-- A concept (sense annotation) within a sentence.
-- Each concept groups one or more words that together denote a single sense.
-- cid is unique within a sentence; the true PK is (sid, cid).
CREATE TABLE concept (
       sid INTEGER
       ,cid INTEGER      -- concept ID within the sentence
       ,clemma TEXT       -- concept lemma (canonical form); may be a multi-word expression
       ,tag TEXT          -- wordnet synset ID (e.g. '02084071-n'), or a meta-tag:
                          --   'e' = tokenization/lemmatization error (corpus should be fixed)
                          --   'w' = wordnet needs enhancement (missing synset or lemma)
                          --   'x' = should not be in wordnet (bad MWE, closed-class POS)
                          -- or a named-entity type (when ntag is also set):
                          --   'per', 'org', 'loc', 'dat', 'num', 'oth', 'nam'
       ,tags TEXT         -- candidate synset IDs offered to annotators for selection
       ,comment TEXT      -- annotator comment; for missing senses uses conventions:
                          --   '=SSID' synonym of synset, '<SSID' hyponym of,
                          --   '!SSID' antonym of, '~SSID' related to
       ,ntag TEXT         -- named-entity subtype: 'org', 'loc', 'per', 'dat',
                          -- 'num', 'oth', 'nam' (generic); NULL for non-NE concepts
       ,usrname TEXT      -- last annotator username
       ,PRIMARY KEY (sid, cid)
       ,FOREIGN KEY(sid) REFERENCES sent(sid)
);

-- Concept-word link: maps which words belong to which concept.
-- A concept may span multiple words; a word may belong to multiple concepts.
CREATE TABLE cwl (
       sid INTEGER
       ,wid INTEGER      -- word within the sentence
       ,cid INTEGER      -- concept within the sentence
       ,usrname TEXT
);

-- Sentiment annotation on a concept.
-- score is typically -1 (negative), 0 (neutral), or 1 (positive).
CREATE TABLE sentiment (
       sid INTEGER
       ,cid INTEGER
       ,score FLOAT      -- sentiment polarity score
       ,username TEXT
       ,PRIMARY KEY (sid, cid)
       ,FOREIGN KEY(sid) REFERENCES sent(sid)
       ,FOREIGN KEY(cid) REFERENCES concept(cid)
);

-- Chunk (phrase-level syntactic unit) within a sentence.
-- Used for shallow parsing / chunking annotation.
CREATE TABLE chunks (
       sid INTEGER
       ,xid INTEGER      -- chunk ID within the sentence
       ,score FLOAT       -- annotation confidence or quality score
       ,comment TEXT
       ,username TEXT
       ,PRIMARY KEY (sid, xid)
       ,FOREIGN KEY(sid) REFERENCES sent(sid)
);

-- Chunk-word link: maps which words belong to which chunk.
CREATE TABLE xwl (
       sid INTEGER
       ,wid INTEGER
       ,xid INTEGER
       ,username TEXT
       ,PRIMARY KEY (sid, wid, xid)
       ,FOREIGN KEY(sid) REFERENCES sent(sid)
       ,FOREIGN KEY(wid) REFERENCES word(wid)
       ,FOREIGN KEY(xid) REFERENCES chunks(xid)
);

-- Error annotation on a sentence.
-- Used to mark translation or language errors.
CREATE TABLE error (
       sid INTEGER
       ,eid INTEGER      -- error ID within the sentence
       ,label TEXT        -- error type label
       ,comment TEXT
       ,username TEXT
       ,PRIMARY KEY (sid, eid)
       ,FOREIGN KEY(sid) REFERENCES sent(sid)
);

-- Error-word link: maps which words are part of an error annotation.
CREATE TABLE ewl (
       sid INTEGER
       ,wid INTEGER
       ,eid INTEGER
       ,username TEXT
       ,PRIMARY KEY (sid, wid, eid)
       ,FOREIGN KEY(sid) REFERENCES sent(sid)
       ,FOREIGN KEY(wid) REFERENCES word(wid)
       ,FOREIGN KEY(eid) REFERENCES error(eid)
);

-- Indexes for frequent query patterns
CREATE INDEX concept_cid ON concept (cid);
CREATE INDEX concept_sid ON concept (sid);
CREATE INDEX concept_clemma ON concept (clemma);
CREATE INDEX sentiment_sid_cid ON concept (sid, cid);
CREATE INDEX cwl_sid ON cwl (sid);
CREATE INDEX cwl_cid ON cwl (cid);
CREATE INDEX word_sid ON word (sid);

-- =========================================================================
-- Audit log tables and triggers
-- Every data table has a corresponding *_log table that records the old
-- and new values on INSERT, UPDATE, and DELETE via AFTER triggers.
-- =========================================================================

CREATE TABLE cwl_log (
       sid_new INTEGER, sid_old INTEGER,
       wid_new INTEGER, wid_old INTEGER,
       cid_new INTEGER, cid_old INTEGER,
       usrname_new TEXT, usrname_old TEXT,
       date_update DATE
);
CREATE TABLE concept_log (
       sid_new INTEGER, sid_old INTEGER,
       cid_new INTEGER, cid_old INTEGER,
       clemma_new TEXT, clemma_old TEXT,
       tag_new TEXT, tag_old TEXT,
       tags_new TEXT, tags_old TEXT,
       comment_new TEXT, comment_old TEXT,
       ntag_new TEXT, ntag_old TEXT,
       usrname_new TEXT, usrname_old TEXT,
       date_update DATE
);
CREATE TABLE sent_log (
       sid_new INTEGER, sid_old INTEGER,
       docID_new INTEGER, docID_old INTEGER,
       pid_new INTEGER, pid_old INTEGER,
       sent_new INTEGER, sent_old INTEGER,
       comment_new INTEGER, comment_old INTEGER,
       usrname_new TEXT, usrname_old TEXT,
       date_update DATE
);
CREATE TABLE word_log (
       sid_new INTEGER, sid_old INTEGER,
       wid_new INTEGER, wid_old INTEGER,
       word_new TEXT, word_old TEXT,
       pos_new TEXT, pos_old TEXT,
       lemma_new TEXT, lemma_old TEXT,
       cfrom_new INTEGER, cfrom_old INTEGER,
       cto_new INTEGER, cto_old INTEGER,
       comment_new INTEGER, comment_old INTEGER,
       usrname_new TEXT, usrname_old TEXT,
       date_update DATE
);
CREATE TABLE sentiment_log (
       sid_new INTEGER, sid_old INTEGER,
       cid_new INTEGER, cid_old INTEGER,
       score_new FLOAT, score_old FLOAT,
       username_new TEXT, username_old TEXT,
       date_update DATE
);
CREATE TABLE chunk_log (
       sid_new INTEGER, sid_old INTEGER,
       xid_new INTEGER, xid_old INTEGER,
       score_new FLOAT, score_old FLOAT,
       comment_new TEXT, comment_old TEXT,
       username_new TEXT, username_old TEXT,
       date_update DATE
);
CREATE TABLE error_log (
       sid_new INTEGER, sid_old INTEGER,
       eid_new INTEGER, eid_old INTEGER,
       label_new TEXT, label_old TEXT,
       comment_new TEXT, comment_old TEXT,
       username_new TEXT, username_old TEXT,
       date_update DATE
);
CREATE TABLE xwl_log (
       sid_new INTEGER, sid_old INTEGER,
       wid_new INTEGER, wid_old INTEGER,
       xid_new INTEGER, xid_old INTEGER,
       username_new TEXT, username_old TEXT,
       date_update DATE
);

-- cwl triggers
CREATE TRIGGER update_cwl_log AFTER UPDATE ON cwl
    BEGIN
    INSERT INTO cwl_log (sid_new, sid_old,
                         wid_new, wid_old,
                         cid_new, cid_old,
                         usrname_new, usrname_old,
                         date_update)
    VALUES (new.sid, old.sid,
            new.wid, old.wid,
            new.cid, old.cid,
            new.usrname, old.usrname,
            DATETIME('NOW'));
    END;
CREATE TRIGGER insert_cwl_log AFTER INSERT ON cwl
    BEGIN
    INSERT INTO cwl_log (sid_new,
                         wid_new,
                         cid_new,
                         usrname_new,
                         date_update)
    VALUES (new.sid,
            new.wid,
            new.cid,
            new.usrname,
            DATETIME('NOW'));
    END;
CREATE TRIGGER delete_cwl_log AFTER DELETE ON cwl
    BEGIN
    INSERT INTO cwl_log (sid_old,
                         wid_old,
                         cid_old,
                         usrname_old,
                         date_update)
    VALUES (old.sid,
            old.wid,
            old.cid,
            old.usrname,
            DATETIME('NOW'));
    END;

-- concept triggers
CREATE TRIGGER update_concept_log AFTER UPDATE ON concept
    BEGIN
    INSERT INTO concept_log (sid_new, sid_old,
                             cid_new, cid_old,
                             clemma_new, clemma_old,
                             tag_new, tag_old,
                             tags_new, tags_old,
                             comment_new, comment_old,
                             ntag_new, ntag_old,
                             usrname_new, usrname_old,
                             date_update)
    VALUES (new.sid, old.sid,
            new.cid, old.cid,
            new.clemma, old.clemma,
            new.tag, old.tag,
            new.tags, old.tags,
            new.comment, old.comment,
            new.ntag, old.ntag,
            new.usrname, old.usrname,
            DATETIME('NOW'));
    END;
CREATE TRIGGER insert_concept_log AFTER INSERT ON concept
    BEGIN
    INSERT INTO concept_log (sid_new,
                             cid_new,
                             clemma_new,
                             tag_new,
                             tags_new,
                             comment_new,
                             ntag_new,
                             usrname_new,
                             date_update)
    VALUES (new.sid,
            new.cid,
            new.clemma,
            new.tag,
            new.tags,
            new.comment,
            new.ntag,
            new.usrname,
            DATETIME('NOW'));
    END;
CREATE TRIGGER delete_concept_log AFTER DELETE ON concept
    BEGIN
    INSERT INTO concept_log (sid_old,
                             cid_old,
                             clemma_old,
                             tag_old,
                             tags_old,
                             comment_old,
                             ntag_old,
                             usrname_old,
                             date_update)
    VALUES (old.sid,
            old.cid,
            old.clemma,
            old.tag,
            old.tags,
            old.comment,
            old.ntag,
            old.usrname,
            DATETIME('NOW'));
    END;

-- sent triggers
CREATE TRIGGER update_sent_log AFTER UPDATE ON sent
    BEGIN
    INSERT INTO sent_log (sid_new, sid_old,
                          docID_new, docID_old,
                          pid_new, pid_old,
                          sent_new, sent_old,
                          comment_new, comment_old,
                          usrname_new, usrname_old,
                          date_update)
    VALUES (new.sid, old.sid,
            new.docID, old.docID,
            new.pid, old.pid,
            new.sent, old.sent,
            new.comment, old.comment,
            new.usrname, old.usrname,
            DATETIME('NOW'));
    END;
CREATE TRIGGER insert_sent_log AFTER INSERT ON sent
    BEGIN
    INSERT INTO sent_log (sid_new,
                          docID_new,
                          pid_new,
                          sent_new,
                          comment_new,
                          usrname_new,
                          date_update)
    VALUES (new.sid,
            new.docID,
            new.pid,
            new.sent,
            new.comment,
            new.usrname,
            DATETIME('NOW'));
    END;
CREATE TRIGGER delete_sent_log AFTER DELETE ON sent
    BEGIN
    INSERT INTO sent_log (sid_old,
                          docID_old,
                          pid_old,
                          sent_old,
                          comment_old,
                          usrname_old,
                          date_update)
    VALUES (old.sid,
            old.docID,
            old.pid,
            old.sent,
            old.comment,
            old.usrname,
            DATETIME('NOW'));
    END;

-- word triggers
CREATE TRIGGER update_word_log AFTER UPDATE ON word
    BEGIN
    INSERT INTO word_log (sid_new, sid_old,
                          wid_new, wid_old,
                          word_new, word_old,
                          pos_new, pos_old,
                          lemma_new, lemma_old,
                          cfrom_new, cfrom_old,
                          cto_new, cto_old,
                          comment_new, comment_old,
                          usrname_new, usrname_old,
                          date_update)
    VALUES (new.sid, old.sid,
            new.wid, old.wid,
            new.word, old.word,
            new.pos, old.pos,
            new.lemma, old.lemma,
            new.cfrom, old.cfrom,
            new.cto, old.cto,
            new.comment, old.comment,
            new.usrname, old.usrname,
            DATETIME('NOW'));
    END;
CREATE TRIGGER insert_word_log AFTER INSERT ON word
    BEGIN
    INSERT INTO word_log (sid_new,
                          wid_new,
                          word_new,
                          pos_new,
                          lemma_new,
                          cfrom_new,
                          cto_new,
                          comment_new,
                          usrname_new,
                          date_update)
    VALUES (new.sid,
            new.wid,
            new.word,
            new.pos,
            new.lemma,
            new.cfrom,
            new.cto,
            new.comment,
            new.usrname,
            DATETIME('NOW'));
    END;
CREATE TRIGGER delete_word_log AFTER DELETE ON word
    BEGIN
    INSERT INTO word_log (sid_old,
                          wid_old,
                          word_old,
                          pos_old,
                          lemma_old,
                          cfrom_old,
                          cto_old,
                          comment_old,
                          usrname_old,
                          date_update)
    VALUES (old.sid,
            old.wid,
            old.word,
            old.pos,
            old.lemma,
            old.cfrom,
            old.cto,
            old.comment,
            old.usrname,
            DATETIME('NOW'));
    END;

-- sentiment triggers
CREATE TRIGGER delete_sentiment_log AFTER DELETE ON sentiment
    BEGIN
    INSERT INTO sentiment_log (sid_old,
                               cid_old,
                               score_old,
                               username_old,
                               date_update)
    VALUES (old.sid,
            old.cid,
            old.score,
            old.username,
            DATETIME('NOW'));
    END;
CREATE TRIGGER insert_sentiment_log AFTER INSERT ON sentiment
    BEGIN
    INSERT INTO sentiment_log (sid_new,
                               cid_new,
                               score_new,
                               username_new,
                               date_update)
    VALUES (new.sid,
            new.cid,
            new.score,
            new.username,
            DATETIME('NOW'));
    END;
