-- Change-log triggers for the NTU-MC corpus databases (eng/cmn/jpn/...).
-- Taken from the 2025-02 server eng.db, whose triggers are all valid.
-- Used by scripts/2026-07/restore_triggers.py; one statement per trigger.

CREATE TRIGGER delete_concept_log AFTER DELETE ON concept
    BEGIN
    INSERT INTO concept_log  (sid_old,
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

CREATE TRIGGER insert_concept_log AFTER INSERT ON concept
    BEGIN
    INSERT INTO concept_log  (sid_new,
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

CREATE TRIGGER update_concept_log AFTER UPDATE ON concept
    BEGIN
    INSERT INTO concept_log  (sid_new, sid_old,
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

CREATE TRIGGER delete_cwl_log AFTER DELETE ON cwl
    BEGIN
    INSERT INTO cwl_log  (sid_old,
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

CREATE TRIGGER insert_cwl_log AFTER INSERT ON cwl
    BEGIN
    INSERT INTO cwl_log  (sid_new,
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

CREATE TRIGGER delete_sent_log AFTER DELETE ON sent
    BEGIN
    INSERT INTO sent_log  (sid_old,
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

CREATE TRIGGER insert_sent_log AFTER INSERT ON sent
    BEGIN
    INSERT INTO sent_log  (sid_new,
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

CREATE TRIGGER delete_sentiment_log
                 AFTER DELETE ON sentiment
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

CREATE TRIGGER insert_sentiment_log
                 AFTER INSERT ON sentiment
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

CREATE TRIGGER insert_word_log AFTER INSERT ON word
    BEGIN
    INSERT INTO word_log  (sid_new,
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

