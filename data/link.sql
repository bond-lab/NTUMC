CREATE TABLE meta (
        -- e.g. for link eng-jpn.db 
	fcorpus TEXT,  -- eng.db
	flang   TEXT,  -- eng
	tcorpus TEXT,  -- jpn.db
	tlang   TEXT,  -- jpn
	comment TEXT
	);
CREATE TABLE slink (
       --   link sentences 
	slid INTEGER PRIMARY KEY,  
	fsid INTEGER NOT NULL,  -- sid in fcorpus
	tsid INTEGER NOT NULL,  -- sid in tcorpus
	ltype TEXT,  -- leave blank for now
	conf FLOAT,  -- 0 - 1.0
	comment TEXT,
	usrname TEXT, -- who added the link
	UNIQUE(fsid, tsid) ON CONFLICT IGNORE
	);
CREATE TABLE clink (
       --   link concepts
	clid INTEGER PRIMARY KEY,
	fsid INTEGER NOT NULL,
	fcid INTEGER NOT NULL,
	tsid INTEGER NOT NULL,
	tcid INTEGER NOT NULL,
	ltype TEXT,
	conf FLOAT,
	comment TEXT,
	usrname TEXT,
	UNIQUE(fcid, fsid, tsid, tcid) ON CONFLICT IGNORE
	);
CREATE TABLE wlink (
       --   link words
	wlid INTEGER PRIMARY KEY,
	fsid INTEGER NOT NULL,
	fwid INTEGER NOT NULL,
	tsid INTEGER NOT NULL,
	twid INTEGER NOT NULL,
	ltype TEXT,
	conf FLOAT,
	comment TEXT,
	usrname TEXT,
	UNIQUE(fsid, fwid, tsid, twid) ON CONFLICT IGNORE
	);
CREATE TABLE slink_log
                 (fsid_new INTEGER, fsid_old INTEGER,
                  tsid_new INTEGER, tsid_old INTEGER, 
                  ltype_new TEXT, ltype_old TEXT,
                  conf_new FLOAT, conf_old FLOAT,
                  comment_new TEXT, comment_old TEXT,
                  usrname_new TEXT, usrname_old TEXT,
                  date_update DATE);
CREATE TRIGGER delete_slink_log
                 AFTER DELETE ON slink
                 BEGIN
                 INSERT INTO slink_log (fsid_old,
                                        tsid_old,
                                        ltype_old,
                                        conf_old,
                                        comment_old,
                                        usrname_old,
                                        date_update)
                 VALUES (old.fsid,
                         old.tsid,
                         old.ltype,
                         old.conf,
                         old.comment,
                         old.usrname,
                         DATETIME('NOW'));
                 END;
CREATE TRIGGER insert_slink_log
                 AFTER INSERT ON slink
                 BEGIN
                 INSERT INTO slink_log (fsid_new,
                                        tsid_new,
                                        ltype_new,
                                        conf_new,
                                        comment_new,
                                        usrname_new,
                                        date_update) 
                 VALUES (new.fsid,
                         new.tsid,
                         new.ltype,
                         new.conf,
                         new.comment,
                         new.usrname,
                         DATETIME('NOW'));
                 END;
