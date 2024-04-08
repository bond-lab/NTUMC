#output a corpus as a profile
import os
import sqlite3
import delphin


db = '/var/www/ntumc/db/eng.db'

docs = ['danc']

outdir = 'danc'
ino = 100

for doc in docs:
    if os.path.exists(db):
        con = sqlite3.connect(db)
        c = con.cursor()
    else:
        print(f"Can't find db: {db}")
        next
    
    c.execute("""SELECT docid,doc,title,url, subtitle, corpusID 
    FROM doc WHERE doc = ?
    """,  (doc,))
    (docid, doc, title, url, subtitle, corpusID) = c.fetchone()   

    #print(docid, doc, title, url, subtitle)
    c.execute("""SELECT sid, sent 
    FROM sent WHERE docid = ?
    """,  (docid,))
    fh = open ('sents.txt', 'w')
    print("i-id", "i-input", "i-comment", sep='\t', file=fh)
    for (sid, sent) in c:
        print(ino, sent, f'sid={sid}', sep='\t', file=fh)
        ino +=1
    
# delphin mkprof --relations Relations  --skeleton --input sents.txt danc

