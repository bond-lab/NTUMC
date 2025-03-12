CREATE TABLE meta (attr TEXT,
                   lang TEXT,
                   val TEXT);
CREATE TABLE pos_def (pos TEXT,
		      lang TEXT,
		      def TEXT);
CREATE TABLE link_def (link TEXT,
 		       lang TEXT,
		       def TEXT);
CREATE TABLE ancestor (synset1 TEXT,
                       synset2 TEXT,
                       hops INTEGER);
CREATE TABLE senslink (synset1 TEXT,
                       wordid1 INTEGER,
                       synset2 TEXT,
                       wordid2 INTEGER,
                       link TEXT,
		       src TEXT, usr TEXT);
CREATE TABLE syselink (synset1 TEXT,
                       synset2 TEXT,
                       wordid2 INTEGER,
                       link TEXT,
		       src TEXT, usr TEXT);
CREATE TABLE variant (varid INTEGER primary key,
                      wordid INTEGER,
                      lang TEXT,
                      lemma TEXT,
                      vartype TEXT, usr TEXT);
CREATE TABLE xlink (synset TEXT,
                    resource TEXT,
                    xref  TEXT,
                    misc TEXT,
                    confidence TEXT, usr TEXT);
CREATE TABLE core (synset TEXT, 
                   core INTEGER);
CREATE INDEX ancestor_synset1_idx ON ancestor (synset1);
CREATE INDEX ancestor_synset2_idx ON ancestor (synset2);
CREATE INDEX xlink_synset_resource_idx ON xlink (synset,resource);
CREATE TABLE xlinks (synset text,
                    wordid integer,
                    lang text,
                    resource text,
                    xref  text,
                    misc text,
                    confidence text, usr TEXT);
CREATE TABLE sense_log (
                    synset_new TEXT, synset_old TEXT,
                    wordid_new INTEGER, wordid_old INTEGER,
                    lang_new TEXT, lang_old TEXT,
                    rank_new TEXT, rank_old TEXT,
                    lexid_new INTEGER, lexid_old INTEGER,
                    freq_new INTEGER, freq_old INTEGER,
                    src_new TEXT, src_old TEXT,
                    confidence_new REAL, confidence_old REAL,
                    usr_new TEXT, usr_old TEXT,
                    date_update DATE);
CREATE TABLE synset_log (
                    synset_new TEXT, synset_old TEXT,
                    pos_new TEXT, pos_old TEXT,
                    name_new TEXT, name_old TEXT,
                    src_new TEXT, src_old TEXT,
                    usr_new TEXT, usr_old TEXT,
                    date_update DATE);
CREATE TABLE synset_def_log (synset_new TEXT, synset_old TEXT,
                                    lang_new TEXT, lang_old TEXT,
                                    def_new TEXT, def_old TEXT,
                                    sid_new INTEGER, sid_old INTEGER,
                                    usr_new TEXT, usr_old TEXT,
                                    date_update DATE);
CREATE TABLE synset_ex_log (synset_new TEXT, synset_old TEXT,
                                   lang_new TEXT, lang_old TEXT,
                                   def_new TEXT, def_old TEXT,
                                   sid_new INTEGER, sid_old INTEGER,
                                   usr_new TEXT, usr_old TEXT,
                                   date_update DATE);
CREATE TABLE word_log (wordid_new INTEGER, wordid_old INTEGER,
                              lang_new TEXT, lang_old TEXT,
                              lemma_new TEXT, lemma_old TEXT,
                              pron_new TEXT, pron_old TEXT,
                              pos_new TEXT, pos_old TEXT,
                              usr_new TEXT, usr_old TEXT,
                              date_update DATE);
CREATE TABLE synlink_log (synset1_new TEXT, synset1_old TEXT,
                                 synset2_new TEXT, synset2_old TEXT,
                                 link_new TEXT, link_old TEXT,
                                 src_new TEXT, src_old TEXT,
                                 usr_new TEXT, usr_old TEXT,
                                 date_update DATE);
CREATE TABLE senslink_log (synset1_new TEXT, synset1_old TEXT,
                                  wordid1_new INTEGER, wordid1_old INTEGER,
                                  synset2_new TEXT, synset2_old TEXT,
                                  wordid2_new INTEGER, wordid2_old INTEGER,
                                  link_new TEXT, link_old TEXT,
                                  src_new TEXT, src_old TEXT,
                                  usr_new TEXT, usr_old TEXT,
                                  date_update DATE);
CREATE TABLE syselink_log (synset1_new TEXT, synset1_old TEXT,
                                  synset2_new TEXT, synset2_old TEXT,
                                  wordid2_new INTEGER, wordid2_old INTEGER,
                                  link_new TEXT, link_old TEXT,
                                  src_new TEXT, src_old TEXT,
                                  usr_new TEXT, usr_old TEXT,
                                  date_update DATE);
CREATE TABLE variant_log (varid_new INTEGER, varid_old INTEGER,
                                 wordid_new INTEGER, wordid_old INTEGER,
                                 lang_new TEXT, lang_old TEXT,
                                 lemma_new TEXT, lemma_old TEXT,
                                 vartype_new TEXT, vartype_old TEXT,
                                 usr_new TEXT, usr_old TEXT,
                                 date_update DATE);
CREATE TABLE xlink_log (synset_new TEXT, synset_old TEXT,
                               resource_new TEXT, resource_old TEXT,
                               xref_new  TEXT, xref_old TEXT,
                               misc_new TEXT, misc_old TEXT,
                               confidence_new TEXT, confidence_old TEXT,
                               usr_new TEXT, usr_old TEXT,
                               date_update DATE);
CREATE TABLE xlinks_log (synset_new TEXT, synset_old TEXT,
                                wordid_new INTEGER, wordid_old INTEGER,
                                lang_new TEXT, lang_old TEXT,
                                resource_new TEXT, resource_old TEXT,
                                xref_new  TEXT, xref_old TEXT,
                                misc_new TEXT, misc_old TEXT,
                                confidence_new TEXT, confidence_old TEXT,
                                usr_new TEXT, usr_old TEXT,
                                date_update DATE);
CREATE TABLE IF NOT EXISTS "synset_def" (synset TEXT,
                          lang TEXT,
                          def TEXT,
                          sid INTEGER,
                          usr TEXT);
CREATE TABLE IF NOT EXISTS "synset_ex" (synset TEXT,
		         lang TEXT,
		         def TEXT,
                         sid INTEGER,
                         usr TEXT);
CREATE TABLE IF NOT EXISTS "synset" (synset TEXT primary key,
         	      pos TEXT,
                      name TEXT,
		      src TEXT,
                      usr TEXT);
CREATE TABLE IF NOT EXISTS "word" (wordid INTEGER primary key,
                    lang TEXT,
                    lemma TEXT,
                    pron TEXT,
                    pos TEXT,
                    usr TEXT);
CREATE TABLE IF NOT EXISTS "sense" (synset TEXT,
                     wordid INTEGER,
                     lang TEXT,
                     rank TEXT,
                     lexid INTEGER,
                     freq INTEGER,
                     src TEXT,
                     confidence REAL,
                     usr TEXT,
                     FOREIGN KEY(synset) REFERENCES "synset"(synset),
                     FOREIGN KEY(wordid) REFERENCES "word"(wordid));
CREATE TABLE IF NOT EXISTS "synlink" (synset1 TEXT,
                       synset2 TEXT,
                       link TEXT,
	               src TEXT,
                       usr TEXT,
                       FOREIGN KEY(synset1) REFERENCES "synset"(synset),
                       FOREIGN KEY(synset2) REFERENCES "synset"(synset));
CREATE INDEX word_id_idx ON word (wordid);
CREATE INDEX word_lemma_idx ON word (lemma);
CREATE INDEX sense_wordid_idx ON sense (wordid);
CREATE INDEX synlink_idx ON synlink (synset1, link);
CREATE INDEX synset_id_idx ON synset (synset);
CREATE INDEX synset_def_id_idx ON synset_def (synset);
CREATE INDEX synset_ex_id_idx ON synset_ex (synset);
CREATE INDEX sense_synset_wordid_lang_idx ON sense (synset, wordid, lang);
CREATE TRIGGER update_sense_log AFTER UPDATE ON sense
    BEGIN
    INSERT INTO sense_log (
                    synset_new, synset_old,
                    wordid_new, wordid_old,
                    lang_new, lang_old,
                    rank_new, rank_old,
                    lexid_new, lexid_old,
                    freq_new, freq_old,
                    src_new, src_old,
                    confidence_new, confidence_old,
                    usr_new, usr_old,
                    date_update)
    VALUES (
        new.synset, old.synset,
        new.wordid, old.wordid,
        new.lang, old.lang,
        new.rank, old.rank,
        new.lexid, old.lexid,
        new.freq, old.freq,
        new.src, old.src,
        new.confidence, old.confidence,
        new.usr, old.usr,
        DATETIME('NOW'));
    END;
CREATE TRIGGER insert_sense_log AFTER INSERT ON sense
    BEGIN
    INSERT INTO sense_log (
                    synset_new,
                    wordid_new,
                    lang_new,
                    rank_new,
                    lexid_new,
                    freq_new,
                    src_new,
                    confidence_new,
                    usr_new,
                    date_update)
    VALUES (
        new.synset,
        new.wordid,
        new.lang,
        new.rank,
        new.lexid,
        new.freq,
        new.src,
        new.confidence,
        new.usr,
        DATETIME('NOW'));
    END;
CREATE TRIGGER delete_sense_log AFTER DELETE ON sense
    BEGIN
    INSERT INTO sense_log (
                    synset_old,
                    wordid_old,
                    lang_old,
                    rank_old,
                    lexid_old,
                    freq_old,
                    src_old,
                    confidence_old,
                    usr_old,
                    date_update)
    VALUES (
        old.synset,
        old.wordid,
        old.lang,
        old.rank,
        old.lexid,
        old.freq,
        old.src,
        old.confidence,
        old.usr,
        DATETIME('NOW'));
    END;
CREATE TRIGGER update_synset_log AFTER UPDATE ON synset
    BEGIN
    INSERT INTO synset_log (
                    synset_new, synset_old,
                    pos_new, pos_old,
                    name_new, name_old,
                    src_new, src_old,
                    usr_new, usr_old,
                    date_update)
    VALUES (
        new.synset, old.synset,
        new.pos, old.pos,
        new.name, old.name,
        new.src, old.src,
        new.usr, old.usr,
        DATETIME('NOW'));
    END;
CREATE TRIGGER insert_synset_log AFTER INSERT ON synset
    BEGIN
    INSERT INTO synset_log (
                    synset_new,
                    pos_new,
                    name_new,
                    src_new,
                    usr_new,
                    date_update)
    VALUES (
        new.synset,
        new.pos,
        new.name,
        new.src,
        new.usr,
        DATETIME('NOW'));
    END;
CREATE TRIGGER delete_synset_log AFTER DELETE ON synset
    BEGIN
    INSERT INTO synset_log (
                    synset_old,
                    pos_old,
                    name_old,
                    src_old,
                    usr_old,
                    date_update)
    VALUES (
        old.synset,
        old.pos,
        old.name,
        old.src,
        old.usr,
        DATETIME('NOW'));
    END;
CREATE TRIGGER update_synset_def_log AFTER UPDATE ON synset_def
    BEGIN
    INSERT INTO synset_def_log (
                        synset_new, synset_old,
                        lang_new, lang_old,
                        def_new, def_old,
                        sid_new, sid_old,
                        usr_new, usr_old,
                        date_update)

    VALUES (
            new.synset, old.synset,
            new.lang, old.lang,
            new.def, old.def,
            new.sid, old.sid,
            new.usr, old.usr,
            DATETIME('NOW'));
    END;
CREATE TRIGGER insert_synset_def_log AFTER INSERT ON synset_def
    BEGIN
    INSERT INTO synset_def_log (
                        synset_new,
                        lang_new,
                        def_new,
                        sid_new,
                        usr_new,
                        date_update)
    VALUES (
            new.synset,
            new.lang,
            new.def,
            new.sid,
            new.usr,
            DATETIME('NOW'));
    END;
CREATE TRIGGER delete_synset_def_log AFTER DELETE ON synset_def
    BEGIN
    INSERT INTO synset_def_log (
                        synset_old,
                        lang_old,
                        def_old,
                        sid_old,
                        usr_old,
                        date_update)
    VALUES (
            old.synset,
            old.lang,
            old.def,
            old.sid,
            old.usr,
            DATETIME('NOW'));
    END;
CREATE TRIGGER update_synset_ex_log AFTER UPDATE ON synset_ex
    BEGIN
    INSERT INTO synset_ex_log (
                        synset_new, synset_old,
                        lang_new, lang_old,
                        def_new, def_old,
                        sid_new, sid_old,
                        usr_new, usr_old,
                        date_update)

    VALUES (
            new.synset, old.synset,
            new.lang, old.lang,
            new.def, old.def,
            new.sid, old.sid,
            new.usr, old.usr,
            DATETIME('NOW'));
    END;
CREATE TRIGGER insert_synset_ex_log AFTER INSERT ON synset_ex
    BEGIN
    INSERT INTO synset_ex_log (
                        synset_new,
                        lang_new,
                        def_new,
                        sid_new,
                        usr_new,
                        date_update)
    VALUES (
            new.synset,
            new.lang,
            new.def,
            new.sid,
            new.usr,
            DATETIME('NOW'));
    END;
CREATE TRIGGER delete_synset_ex_log AFTER DELETE ON synset_ex
    BEGIN
    INSERT INTO synset_ex_log (
                        synset_old,
                        lang_old,
                        def_old,
                        sid_old,
                        usr_old,
                        date_update)
    VALUES (
            old.synset,
            old.lang,
            old.def,
            old.sid,
            old.usr,
            DATETIME('NOW'));
    END;
CREATE TRIGGER update_word_log AFTER UPDATE ON word
    BEGIN
    INSERT INTO word_log (
                  wordid_new, wordid_old,
                  lang_new, lang_old,
                  lemma_new, lemma_old,
                  pron_new, pron_old,
                  pos_new, pos_old,
                  usr_new, usr_old,
                  date_update)
    VALUES (
          new.wordid, old.wordid,
          new.lang, old.lang,
          new.lemma, old.lemma,
          new.pron, old.pron,
          new.pos, old.pos,
          new.usr, old.usr,
          DATETIME('NOW'));
    END;
CREATE TRIGGER insert_word_log AFTER INSERT ON word
    BEGIN
    INSERT INTO word_log (
                  wordid_new,
                  lang_new,
                  lemma_new,
                  pron_new,
                  pos_new,
                  usr_new,
                  date_update)
    VALUES (
          new.wordid,
          new.lang,
          new.lemma,
          new.pron,
          new.pos,
          new.usr,
          DATETIME('NOW'));
    END;
CREATE TRIGGER delete_word_log AFTER DELETE ON word
    BEGIN
    INSERT INTO word_log (
                  wordid_old,
                  lang_old,
                  lemma_old,
                  pron_old,
                  pos_old,
                  usr_old,
                  date_update)
    VALUES (
          old.wordid,
          old.lang,
          old.lemma,
          old.pron,
          old.pos,
          old.usr,
          DATETIME('NOW'));
    END;
CREATE TRIGGER update_synlink_log AFTER UPDATE ON synlink
    BEGIN
    INSERT INTO synlink_log (
                         synset1_new, synset1_old,
                         synset2_new, synset2_old,
                         link_new, link_old,
                         src_new, src_old,
                         usr_new, usr_old,
                         date_update)
    VALUES (
           new.synset1, old.synset1,
           new.synset2, old.synset2,
           new.link, old.link,
           new.src, old.src,
           new.usr, old.usr,
           DATETIME('NOW'));
    END;
CREATE TRIGGER insert_synlink_log AFTER INSERT ON synlink
    BEGIN
    INSERT INTO synlink_log (
                         synset1_new,
                         synset2_new,
                         link_new,
                         src_new,
                         usr_new,
                         date_update)
    VALUES (
           new.synset1,
           new.synset2,
           new.link,
           new.src,
           new.usr,
           DATETIME('NOW'));
    END;
CREATE TRIGGER delete_synlink_log AFTER DELETE ON synlink
    BEGIN
    INSERT INTO synlink_log (
                         synset1_old,
                         synset2_old,
                         link_old,
                         src_old,
                         usr_old,
                         date_update)
    VALUES (
           old.synset1,
           old.synset2,
           old.link,
           old.src,
           old.usr,
           DATETIME('NOW'));
    END;
CREATE TRIGGER update_senslink_log AFTER UPDATE ON senslink
    BEGIN
    INSERT INTO senslink_log (
                          synset1_new, synset1_old,
                          wordid1_new, wordid1_old,
                          synset2_new, synset2_old,
                          wordid2_new, wordid2_old,
                          link_new, link_old,
                          src_new, src_old,
                          usr_new, usr_old,
                          date_update)
    VALUES (
            new.synset1, old.synset1,
            new.wordid1, old.wordid1,
            new.synset2, old.synset2,
            new.wordid2, old.wordid2,
            new.link, old.link,
            new.src, old.src,
            new.usr, old.usr,
            DATETIME('NOW'));
    END;
CREATE TRIGGER insert_senslink_log AFTER INSERT ON senslink
    BEGIN
    INSERT INTO senslink_log (
                          synset1_new,
                          wordid1_new,
                          synset2_new,
                          wordid2_new,
                          link_new,
                          src_new,
                          usr_new,
                          date_update)
    VALUES (
            new.synset1,
            new.wordid1,
            new.synset2,
            new.wordid2,
            new.link,
            new.src,
            new.usr,
            DATETIME('NOW'));
    END;
CREATE TRIGGER delete_senslink_log AFTER DELETE ON senslink
    BEGIN
    INSERT INTO senslink_log (
                          synset1_old,
                          wordid1_old,
                          synset2_old,
                          wordid2_old,
                          link_old,
                          src_old,
                          usr_old,
                          date_update)
    VALUES (
            old.synset1,
            old.wordid1,
            old.synset2,
            old.wordid2,
            old.link,
            old.src,
            old.usr,
            DATETIME('NOW'));
    END;
CREATE TRIGGER update_syselink_log AFTER UPDATE ON syselink
    BEGIN
    INSERT INTO syselink_log (
                          synset1_new, synset1_old,
                          synset2_new, synset2_old,
                          wordid2_new, wordid2_old,
                          link_new, link_old,
                          src_new, src_old,
                          usr_new, usr_old,
                          date_update)
    VALUES (
            new.synset1, old.synset1,
            new.synset2, old.synset2,
            new.wordid2, old.wordid2,
            new.link, old.link,
            new.src, old.src,
            new.usr, old.usr,
            DATETIME('NOW'));
    END;
CREATE TRIGGER insert_syselink_log AFTER INSERT ON syselink
    BEGIN
    INSERT INTO syselink_log (
                          synset1_new,
                          synset2_new,
                          wordid2_new,
                          link_new,
                          src_new,
                          usr_new,
                          date_update)
    VALUES (
            new.synset1,
            new.synset2,
            new.wordid2,
            new.link,
            new.src,
            new.usr,
            DATETIME('NOW'));
    END;
CREATE TRIGGER delete_syselink_log AFTER DELETE ON syselink
    BEGIN
    INSERT INTO syselink_log (
                          synset1_old,
                          synset2_old,
                          wordid2_old,
                          link_old,
                          src_old,
                          usr_old,
                          date_update)
    VALUES (
            old.synset1,
            old.synset2,
            old.wordid2,
            old.link,
            old.src,
            old.usr,
            DATETIME('NOW'));
    END;
CREATE TRIGGER update_variant_log AFTER UPDATE ON variant
    BEGIN
    INSERT INTO variant_log (
                          varid_new, varid_old,
                          wordid_new, wordid_old,
                          lang_new, lang_old,
                          lemma_new, lemma_old,
                          vartype_new, vartype_old,
                          usr_new, usr_old,
                          date_update)
    VALUES (
            new.varid, old.varid,
            new.wordid, old.wordid,
            new.lang, old.lang,
            new.lemma, old.lemma,
            new.vartype, old.vartype,
            new.usr, old.usr,
            DATETIME('NOW'));
    END;
CREATE TRIGGER insert_variant_log AFTER INSERT ON variant
    BEGIN
    INSERT INTO variant_log (
                          varid_new,
                          wordid_new,
                          lang_new,
                          lemma_new,
                          vartype_new,
                          usr_new,
                          date_update)
    VALUES (
            new.varid,
            new.wordid,
            new.lang,
            new.lemma,
            new.vartype,
            new.usr,
            DATETIME('NOW'));
    END;
CREATE TRIGGER delete_variant_log AFTER DELETE ON variant
    BEGIN
    INSERT INTO variant_log (
                          varid_old,
                          wordid_old,
                          lang_old,
                          lemma_old,
                          vartype_old,
                          usr_old,
                          date_update)
    VALUES (
            old.varid,
            old.wordid,
            old.lang,
            old.lemma,
            old.vartype,
            old.usr,
            DATETIME('NOW'));
    END;
CREATE TRIGGER update_xlink_log AFTER UPDATE ON xlink
    BEGIN
    INSERT INTO xlink_log (
                   synset_new, synset_old,
                   resource_new, resource_old,
                   xref_new, xref_old,
                   misc_new, misc_old,
                   confidence_new, confidence_old,
                   usr_new, usr_old,
                   date_update)
    VALUES (
           new.synset, old.synset,
           new.resource, old.resource,
           new.xref, old.xref,
           new.misc, old.misc,
           new.confidence, old.confidence,
           new.usr, old.usr,
           DATETIME('NOW'));
    END;
CREATE TRIGGER insert_xlink_log AFTER INSERT ON xlink
    BEGIN
    INSERT INTO xlink_log (
                   synset_new,
                   resource_new,
                   xref_new,
                   misc_new,
                   confidence_new,
                   usr_new,
                   date_update)
    VALUES (
           new.synset,
           new.resource,
           new.xref,
           new.misc,
           new.confidence,
           new.usr,
           DATETIME('NOW'));
    END;
CREATE TRIGGER delete_xlink_log AFTER DELETE ON xlink
    BEGIN
    INSERT INTO xlink_log (
                   synset_old,
                   resource_old,
                   xref_old,
                   misc_old,
                   confidence_old,
                   usr_old,
                   date_update)
    VALUES (
           old.synset,
           old.resource,
           old.xref,
           old.misc,
           old.confidence,
           old.usr,
           DATETIME('NOW'));
    END;
CREATE TRIGGER update_xlinks_log AFTER UPDATE ON xlinks
    BEGIN
    INSERT INTO xlinks_log (
                   synset_new, synset_old,
                   wordid_new, wordid_old,
                   lang_new, lang_old,
                   resource_new, resource_old,
                   xref_new, xref_old,
                   misc_new, misc_old,
                   confidence_new, confidence_old,
                   usr_new, usr_old,
                   date_update)
    VALUES (
           new.synset, old.synset,
           new.wordid, old.wordid,
           new.lang, old.lang,
           new.resource, old.resource,
           new.xref, old.xref,
           new.misc, old.misc,
           new.confidence, old.confidence,
           new.usr, old.usr,
           DATETIME('NOW'));
    END;
CREATE TRIGGER insert_xlinks_log AFTER INSERT ON xlinks
    BEGIN
    INSERT INTO xlinks_log (
                   synset_new,
                   wordid_new,
                   lang_new,
                   resource_new,
                   xref_new,
                   misc_new,
                   confidence_new,
                   usr_new,
                   date_update)
    VALUES (
           new.synset,
           new.wordid,
           new.lang,
           new.resource,
           new.xref,
           new.misc,
           new.confidence,
           new.usr,
           DATETIME('NOW'));
    END;
CREATE TRIGGER delete_xlinks_log AFTER DELETE ON xlinks
    BEGIN
    INSERT INTO xlinks_log (
                   synset_old,
                   wordid_old,
                   lang_old,
                   resource_old,
                   xref_old,
                   misc_old,
                   confidence_old,
                   usr_old,
                   date_update)
    VALUES (
           old.synset,
           old.wordid,
           old.lang,
           old.resource,
           old.xref,
           old.misc,
           old.confidence,
           old.usr,
           DATETIME('NOW'));
    END;
CREATE TABLE IF NOT EXISTS "synset_comment" (
synset TEXT NOT NULL,
comment TEXT NOT NULL,
u TEXT NOT NULL,
t TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX synset_comment_id_idx ON synset_comment (synset);
CREATE TABLE synset_comment_log (
synset_new TEXT, synset_old TEXT,
comment_new TEXT, comment_old TEXT,
u_new TEXT, u_old TEXT,
t_new TEXT, t_old TEXT,
date_update DATE);
CREATE TRIGGER delete_synset_comment_log
AFTER DELETE ON synset_comment
BEGIN
INSERT INTO synset_comment_log (
                        synset_old,
                        comment_old,
                        u_old,
                        t_old,
                        date_update)
VALUES (
            old.synset,
            old.comment,
            old.u,
            old.t,
            CURRENT_TIMESTAMP);
END;
CREATE TRIGGER insert_synset_comment_log
AFTER INSERT ON synset_comment
BEGIN
INSERT INTO synset_comment_log (
                        synset_new,
                        comment_new,
                        u_new,
                        t_new,
                        date_update)
VALUES (
            new.synset,
            new.comment,
            new.u,
            new.t,
            CURRENT_TIMESTAMP);
END;
CREATE TRIGGER update_synset_comment_log
AFTER UPDATE ON synset_comment
BEGIN
INSERT INTO synset_comment_log (
                        synset_new, synset_old,
                        comment_new, comment_old,
                        u_new, u_old,
                        t_new, t_old,
                        date_update)

VALUES (
            new.synset, old.synset,
            new.comment, old.comment,
            new.u, old.u,
            new.t, old.t,
            CURRENT_TIMESTAMP);
END;
