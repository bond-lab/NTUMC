# Concept Tag Issues

Non-standard `concept.tag` values found during DB audit (2026-06-26).
None of these crash the display pipeline — bad tags pass silently through the WN synset lookup
with no definition shown.  All queries run against `build/*.db`.

---

## 1. `ind.db` — `prn=nya` (720 rows, yoursing corpus only)

Annotator notes stored as a tag.  All 720 occurrences are in `corpusID=4` (yoursing/tourism).
The clemma is always `⨁nya`.

```sql
-- Reproduce
SELECT COUNT(*) FROM concept WHERE tag='prn=nya';
-- 720

SELECT s.sid, co.cid, co.clemma, co.comment
FROM concept co JOIN sent s ON co.sid=s.sid
WHERE co.tag='prn=nya' LIMIT 10;
```

**Possible fix:** change tag to `x` (should not be tagged) or remove the concepts entirely
if they are annotation artefacts.

---

## 2. `eng.db` — `s` tag (246 rows) — uncommitted sense suggestions

The `comment` field on `s`-tagged concepts frequently holds old-format synset IDs
(e.g. `=02794670-a; 00199912-v`), suggesting these were intended as sense candidates
that were never committed to a real synset tag.

```sql
-- Reproduce
SELECT tag, COUNT(*) FROM concept WHERE tag IN ('s','m') GROUP BY tag;
-- m|441  s|246

-- Inspect s-tags with synset candidates in comment
SELECT sid, cid, clemma, tag, comment
FROM concept WHERE tag='s' AND comment != '' LIMIT 20;
```

**Possible fix:** parse the `comment` field and promote the first valid synset ID to `tag`
where it resolves in the WN DB; otherwise set to `u` (untagged).

---

## 3. `eng.db` — `m` tag (441 rows) — multi-word expressions

Multi-word lemmas (e.g. `do_in`, `go_from_strength_to_strength`) tagged `m`.
No comment field content; looks like a legacy code for multi-word expressions.

```sql
SELECT sid, cid, clemma, tag FROM concept WHERE tag='m' LIMIT 10;
```

**Possible fix:** decide whether `m` is a valid tag to keep (add to documentation)
or remap to `u` / `x` depending on whether the expression should be tagged.

---

## 4. `jpn.db` — `s`, `m`, `h` tags (1422 / 546 / 335 rows)

Same informal codes appear in Japanese at much higher volume.

```sql
SELECT tag, COUNT(*) FROM concept WHERE tag IN ('s','m','h') GROUP BY tag;
-- h|335  m|546  s|1422

SELECT sid, cid, clemma, tag, comment FROM concept WHERE tag='h' LIMIT 5;
SELECT sid, cid, clemma, tag, comment FROM concept WHERE tag='s' LIMIT 5;
```

**Possible fix:** same as `eng` — resolve `s`-tagged comments if they contain synset IDs;
determine intended meaning of `h` (possibly "header"?) before remapping.

---

## 5. `cmn.db` — `d` (76 rows) and `h` (25 rows)

Chinese-specific informal tags.  `d`-tagged concepts have clemmas ending in 的 (de),
suggesting they mark adjectival/possessive particles.

```sql
SELECT tag, COUNT(*) FROM concept WHERE tag IN ('d','h') GROUP BY tag;
-- d|76  h|25

SELECT sid, cid, clemma, tag, comment FROM concept WHERE tag='d' LIMIT 5;
SELECT sid, cid, clemma, tag, comment FROM concept WHERE tag='h' LIMIT 5;
```

**Possible fix:** if `d` marks grammatical particles (structural, should-not-tag),
remap to `x`.  Confirm meaning of `h` before acting.

---

## 6. `ces.db` — `dat` tag (3 rows)

Three concepts tagged `dat` — likely date NEs where the standard form is `dat:year`.

```sql
SELECT sid, cid, clemma, tag, comment FROM concept WHERE tag='dat';
-- 110008|39|Bala|dat|
-- 110156|2|čtvrthodinný|dat|a quarter of an hour\n15234942-n;
-- 110162|2|tapa-tapa|dat|
```

**Possible fix:** remap to `dat:year` if they are dates, or to `u` if uncertain.
`110156` has a synset candidate in its comment that could be promoted.

---

## 7. `ind.db` — `ne:org` (4) and `ne:loc` (2) tags

Non-standard NE format.  The canonical tags are bare `org` and `loc`
(without the `ne:` prefix).

```sql
SELECT tag, COUNT(*) FROM concept WHERE tag IN ('ne:org','ne:loc') GROUP BY tag;
-- ne:loc|2  ne:org|4

SELECT sid, cid, clemma, tag FROM concept WHERE tag LIKE 'ne:%';
```

**Possible fix:** strip the `ne:` prefix: `UPDATE concept SET tag='org' WHERE tag='ne:org'`
and similarly for `ne:loc`.  Safe mechanical change.

---

## 8. Sentences with no words (structural/heading sentences)

Not a tag issue but noted here for completeness.  These are structural sentences
(headings, metadata rows) that were not word-tokenised.  The display renders them
as blank sentence blocks.

```sql
SELECT COUNT(DISTINCT sid) FROM sent
WHERE sid NOT IN (SELECT DISTINCT sid FROM word);
```

| DB      | Count |
|---------|------:|
| ces.db  |     2 |
| cmn.db  |  1030 |
| eng.db  |  1674 |
| ind.db  |   915 |
| ita.db  |     0 |
| jpn.db  |  4028 |
| yue.db  |     3 |
| zsm.db  |    78 |

```sql
-- Inspect a sample (replace DB as needed)
SELECT s.sid, s.docID, s.sent
FROM sent s
WHERE s.sid NOT IN (SELECT DISTINCT sid FROM word)
LIMIT 10;
```

---

## 9. Empty `sent.sent` rows (eng: 1, yue: 3)

```sql
SELECT sid, docID, sent FROM sent WHERE sent IS NULL OR sent = '';
```

Cosmetic — renders as a blank line in the document view.

---

## 10. `zsm.db` — missing `sentiment` table

`zsm.db` has no `sentiment` table (all other DBs do).
The display pipeline does not query `sentiment`, so this causes no current error.

```sql
-- Verify (run against zsm.db)
SELECT name FROM sqlite_master WHERE type='table' AND name='sentiment';
-- (0 rows)
```

**Possible fix:** create an empty sentiment table:
```sql
CREATE TABLE sentiment (
    sid     INTEGER,
    cid     INTEGER,
    score   REAL,
    comment TEXT,
    usrname TEXT,
    PRIMARY KEY (sid, cid)
);
```
