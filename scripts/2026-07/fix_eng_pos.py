#!/usr/bin/env python3
"""Apply the 2017-11-17 English POS/tokenisation fixes to eng.db.

Modern port of Junling's fix scripts (work/ntu-mc/2017-11-17: fixpunct.py,
task3consistency.py, fixclem.py), which were tested in 2017 but never
pushed to the server.  The port is content-verified: every hardcoded
(sid, wid) fix carries the surface form it expects (extracted from the
2017 pre-fix database into fix_eng_pos_targets.json) and is skipped with
a log entry when the current database has diverged (the server
retokenised many sentences after 2017).

Phases, in the order of the original pipeline:
  1. pattern POS fixes   - bulk reclassification of legacy tags
                           (Fc/Fp/Fe/Fz/Ft/Fh/Fg/Fd/Frc, brackets, ...)
  2. quote fixes         - possessive POS, open/close quote guessing
  3. hardcoded POS fixes - verified per-token corrections
  4. VAX fixes           - auxiliary verbs to Penn tag + '-VAX' suffix
  5. token splits        - Zm/Zp/Zu currency/percent/unit tokens,
                           GBP amounts, S$ merge
  6. token rewrites      - hand-fixed tokenisation (Sherlock commas)
  7. sentence text fixes - typo corrections in sent.sent
  8. word text fixes     - typo corrections in word.word/lemma
  9. consistency repair  - tokenisation vs sentence text (n't, curly
                           quotes, tabs) + report of residues
 10. clemma/lemma case   - synchronise capitalisation (fixclem port)
 11. offsets             - recompute cfrom/cto for modified sentences

Usage:
    .venv/bin/python scripts/fix_eng_pos.py build/eng.db --dry-run
    .venv/bin/python scripts/fix_eng_pos.py build/eng.db \
        --report build/log/fix_eng_pos.txt
"""

import argparse
import difflib
import json
import logging
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

# fix_cpos lives one level up, in the permanent scripts/ toolbox
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fix_cpos import find_word_offsets  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

TARGETS_FILE = Path(__file__).resolve().parent / "fix_eng_pos_targets.json"

# Penn Treebank tags considered valid after fixing (plus the -VAX
# auxiliary convention already present in the live database).
PENN_TAGS = {
    "CC", "CD", "DT", "EX", "FW", "IN", "JJ", "JJR", "JJS", "LS", "MD",
    "NN", "NNS", "NNP", "NNPS", "PDT", "POS", "PRP", "PRP$", "RB", "RBR",
    "RBS", "RP", "SYM", "TO", "UH", "VB", "VBD", "VBG", "VBN", "VBP",
    "VBZ", "WDT", "WP", "WP$", "WRB", "HYPH", "NFP",
    "“", "”", ",", ".", "-LRB-", "-RRB-", ":", "$",
}

# Legacy (pre-fix) tags that the pattern phase may rewrite.
LEGACY_TAGS = {
    "Fc", "Fx", "Fs", "Fp", "Fat", "Fit", "Fpa", "Fpt", "Fe", "Fz", "Ft",
    "Fh", "Fg", "Fd", "Frc", "VAX", "Zm", "Zp", "Zu", "``", "''", "(", ")",
}

# Auxiliary verb surface form -> Penn tag (fixpunct Task 1.5, extended
# with the two forms found in the current data: did, 've).
VAX_POS = {
    "Be": "VB", "Have": "VB", "be": "VB", "have": "VB",
    "Had": "VBD", "was": "VBD", "were": "VBD", "had": "VBD", "did": "VBD",
    "Having": "VBG", "having": "VBG", "being": "VBG",
    "been": "VBN",
    "Am": "VBP", "am": "VBP", "are": "VBP", "'ve": "VBP",
    "Is": "VBZ", "Has": "VBZ", "is": "VBZ", "has": "VBZ",
}

# Measure / currency nouns for Zm/Zu splits: surface -> (pos, lemma).
UNIT_POS = {
    "dollars": ("NNS", "dollar"), "yen": ("NN", "yen"),
    "baht": ("NNS", "baht"), "marks": ("VBZ", "mark"),
    "kilometers": ("NNS", "kilometer"), "kilogram": ("NN", "kilogram"),
    "kilograms": ("NNS", "kilogram"), "seconds": ("NNS", "second"),
    "second": ("NN", "second"), "meter": ("NN", "meter"),
    "meters": ("NNS", "meter"), "centimeters": ("NNS", "centimeter"),
    "tons": ("NNS", "ton"), "hectares": ("NNS", "hectare"),
    "%": ("NN", "%"), "half": ("NN", "half"), "third": ("NN", "third"),
    "sixth": ("NN", "sixth"), "eleventh": ("NN", "eleventh"),
    "bit": ("NN", "bit"), "million": ("CD", "million"),
    "billion": ("CD", "billion"),
}

NUMBER_WORDS = {
    "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "twenty", "thirty", "forty",
    "fifty", "sixty", "seventy", "eighty", "ninety", "hundred",
}

# Contraction repair tables (task3consistency port).
STRAIGHT_NOT = {
    "don't": "do", "doesn't": "does", "couldn't": "could",
    "haven't": "have", "didn't": "did", "can't": "can",
    "shouldn't": "should", "weren't": "were", "aren't": "are",
    "isn't": "is", "Don't": "do", "won't": "will",
}
CURLY = {
    "’re": "'re", "’ll": "'ll", "’ve": "'ve",
    "’d": "'d", "’m": "'m",
}
CURLY_NOT = {
    "Don’t": "do", "don’t": "do", "won’t": "will",
    "can’t": "can", "haven’t": "have", "doesn’t": "does",
}


class Fixer:
    """Applies the 2017 fix pipeline to one corpus database."""

    def __init__(self, conn: sqlite3.Connection, targets: dict) -> None:
        """Set up with an open connection and the baked target data.

        Args:
            conn: Open connection to the corpus database.
            targets: Parsed fix_eng_pos_targets.json contents.
        """
        self.conn = conn
        self.targets = targets
        self.counts: Counter = Counter()
        self.report: list[str] = []
        self.modified_sids: set[int] = set()

    # -- helpers ---------------------------------------------------------

    def note(self, line: str) -> None:
        """Record a report line."""
        self.report.append(line)

    def upd(self, sql: str, params: tuple = (), tag: str = "update") -> int:
        """Execute an UPDATE/DELETE/INSERT, count affected rows.

        Args:
            sql: Statement with ? placeholders.
            params: Bind values.
            tag: Counter key for the phase summary.

        Returns:
            Number of rows changed.
        """
        cur = self.conn.execute(sql, params)
        n = cur.rowcount if cur.rowcount > 0 else 0
        self.counts[tag] += n
        return n

    def sent_words(self, sid: int) -> list[tuple]:
        """Return ordered (wid, word, pos, lemma) rows for a sentence."""
        return self.conn.execute(
            "SELECT wid, word, pos, lemma FROM word WHERE sid = ? "
            "ORDER BY wid", (sid,)).fetchall()

    def word_at(self, sid: int, wid: int) -> tuple | None:
        """Return (word, pos) at a position, or None."""
        return self.conn.execute(
            "SELECT word, pos FROM word WHERE sid = ? AND wid = ?",
            (sid, wid)).fetchone()

    def set_pos(self, sid: int, wid: int, pos: str, tag: str) -> None:
        """Set the POS of one word and mark the sentence modified."""
        self.upd("UPDATE word SET pos = ? WHERE sid = ? AND wid = ?",
                 (pos, sid, wid), tag)
        self.modified_sids.add(sid)

    def shift_wids(self, sid: int, above: int, delta: int) -> None:
        """Shift word and cwl wids greater than `above` by delta.

        Order of updates avoids UNIQUE collisions on (sid, wid).
        """
        rows = self.conn.execute(
            "SELECT wid FROM word WHERE sid = ? AND wid > ? ORDER BY wid",
            (sid, above)).fetchall()
        ordered = reversed(rows) if delta > 0 else rows
        for (wid,) in ordered:
            self.conn.execute(
                "UPDATE word SET wid = ? WHERE sid = ? AND wid = ?",
                (wid + delta, sid, wid))
            self.conn.execute(
                "UPDATE cwl SET wid = ? WHERE sid = ? AND wid = ?",
                (wid + delta, sid, wid))

    # -- phase 1: pattern POS fixes ---------------------------------------

    def pattern_pos_fixes(self) -> None:
        """Bulk reclassification of legacy POS tags (fixpunct part 1)."""
        u = self.mark_and_update
        # commas: Fc/Fx/Fs, stray comma under Fp, ellipsis/semicolon under :
        u("UPDATE word SET pos = ',' WHERE pos = 'Fp' AND word = ','")
        u("UPDATE word SET pos = ',' WHERE pos IN ('Fc', 'Fx', 'Fs')")
        u("UPDATE word SET pos = ',' WHERE pos = ':' AND word IN ('...', ';')")
        # sentence-final punctuation
        u("UPDATE word SET pos = '.' WHERE pos IN ('Fp', 'Fat', 'Fit')")
        u("UPDATE word SET pos = '.' WHERE word = '!' AND pos IN ('VBP', 'Fpt')")
        # brackets
        u("UPDATE word SET pos = '-LRB-' WHERE pos IN ('Fpa', '(') OR word = '['")
        u("UPDATE word SET pos = '-RRB-' WHERE pos IN ('Fpt', ')') OR word = ']'")
        # stray full stop under Fe
        u("UPDATE word SET pos = '.' WHERE pos = 'Fe' AND word = '.'")
        # symbols and other legacy classes
        u("UPDATE word SET pos = 'SYM' WHERE pos IN ('Frc', 'Ft')")
        u("UPDATE word SET pos = 'SYM' WHERE pos = 'Fz' AND word IN "
          "('*', '**', '***', '>', '+', '\\xA2', '@', '©')")
        u("UPDATE word SET pos = 'CC' WHERE pos = 'Fz' AND word = '&'")
        u("UPDATE word SET pos = ',' WHERE pos = 'Fz' "
          "AND word IN ('....', '......')")
        # heaven mis-taggings
        u("UPDATE word SET pos = 'NNP' WHERE word = 'Heaven' AND pos = 'VB'")
        u("UPDATE word SET pos = 'NN' WHERE word = 'heaven' "
          "AND pos IN ('VB', 'CD', 'RB')")

    def pattern_residual_fixes(self) -> None:
        """Residual legacy tags, after the hardcoded per-token fixes."""
        u = self.mark_and_update
        u("UPDATE word SET pos = ':' WHERE pos IN ('Fd', 'Fz', 'Fg')")
        u("UPDATE word SET pos = 'HYPH' WHERE pos = 'Fh'")
        # plain 'Z' numerals (left behind by the 2017 pipeline): clear
        # numeric or number-word surfaces become CD, the rest is logged
        for sid, wid, word in self.conn.execute(
                "SELECT sid, wid, word FROM word WHERE pos = 'Z'").fetchall():
            if re.fullmatch(r"[0-9][0-9.,:\-/]*", word) or \
                    word.lower() in NUMBER_WORDS:
                self.set_pos(sid, wid, "CD", "pattern")
            else:
                self.note(f"SKIP Z tag sid={sid} wid={wid} {word!r}")

    def mark_and_update(self, sql: str, params: tuple = ()) -> int:
        """Run a bulk UPDATE on word, tracking modified sentences.

        The statement must target the word table; affected sids are
        collected first so offset/consistency phases know what changed.
        """
        where = sql.split("WHERE", 1)[1]
        sids = self.conn.execute(
            f"SELECT DISTINCT sid FROM word WHERE {where}", params).fetchall()
        self.modified_sids.update(s for (s,) in sids)
        return self.upd(sql, params, "pattern")

    # -- phase 2: quotes ---------------------------------------------------

    def quote_fixes(self) -> None:
        """Disambiguate quotation marks and possessives (fixpunct part 5)."""
        conn = self.conn
        # possessive: ' after a word ending in s
        for sid, wid in conn.execute(
                "SELECT sid, wid FROM word WHERE word = '''' AND pos = 'Fe'"
                ).fetchall():
            prev = self.word_at(sid, wid - 1)
            if prev and prev[0].endswith("s"):
                self.set_pos(sid, wid, "POS", "quote")
        # decades and years like '90s, '84 (2017 rule: always NN)
        for sid, wid, pos in conn.execute(
                "SELECT sid, wid, pos FROM word "
                "WHERE word GLOB '''[0-9]*' AND length(word) > 1").fetchall():
            if pos != "NN":
                self.set_pos(sid, wid, "NN", "quote")
        # Fe directly before punctuation closes a quotation
        for sid, wid in conn.execute(
                "SELECT sid, wid FROM word WHERE pos = 'Fe'").fetchall():
            nxt = self.word_at(sid, wid + 1)
            if nxt and nxt[0] in {",", ".", "!", "?"}:
                self.set_pos(sid, wid, "”", "quote")
        # '' as a token is always a closing quote
        sids = self.conn.execute(
            "SELECT DISTINCT sid FROM word WHERE word = ? AND pos IN (?, ?)",
            ("''", "Fe", "''")).fetchall()
        self.modified_sids.update(s for (s,) in sids)
        self.upd("UPDATE word SET pos = '”' WHERE word = ? "
                 "AND pos IN (?, ?)", ("''", "Fe", "''"), "quote")
        # single and double quotes: guess open/close from sentence context
        for word_form, pos_val, ctx in (
                ("'", "Fe", 1), ("'", "''", 2), ('"', "Fe", 2), ('"', "''", 2)):
            self._open_close(word_form, pos_val, ctx)
        # `` opens; whatever still carries '' opens (2017 behaviour)
        self.mark_and_update("UPDATE word SET pos = '“' WHERE pos = '``'")
        self.mark_and_update(
            "UPDATE word SET pos = '“' WHERE word IN ('``', '`') "
            "AND pos = 'Fe'")
        sids = self.conn.execute(
            "SELECT DISTINCT sid FROM word WHERE pos = ?", ("''",)).fetchall()
        self.modified_sids.update(s for (s,) in sids)
        self.upd("UPDATE word SET pos = '“' WHERE pos = ?", ("''",), "quote")

    def _open_close(self, quote: str, pos_val: str, n_context: int) -> None:
        """Classify quote tokens as opening or closing.

        A quote is closing when the preceding word(s) immediately abut it
        in the sentence text (fixpunct's context-matching heuristic).

        Args:
            quote: The quote surface form to consider.
            pos_val: Only rows currently carrying this POS are touched.
            n_context: Number of preceding words to match against.
        """
        rows = self.conn.execute(
            "SELECT sid, wid FROM word WHERE word = ? AND pos = ?",
            (quote, pos_val)).fetchall()
        for sid, wid in rows:
            if wid - n_context < 0:
                self.set_pos(sid, wid, "“", "quote")
                continue
            sent = self.conn.execute(
                "SELECT sent FROM sent WHERE sid = ?", (sid,)).fetchone()
            prevs = [self.word_at(sid, wid - i) for i in range(n_context, 0, -1)]
            if not sent or any(p is None for p in prevs):
                self.set_pos(sid, wid, "“", "quote")
                continue
            # token surfaces encode double quotes as `` / ''
            surfs = [p[0].replace("``", '"').replace("''", '"')
                     for p in prevs]
            joined = "".join(surfs) + quote
            spaced = " ".join(surfs) + quote
            closing = any(
                re.search(rf"{re.escape(cand)}($|\s)", sent[0])
                for cand in (joined, spaced))
            self.set_pos(sid, wid, "”" if closing else "“", "quote")

    # -- phase 3: hardcoded POS fixes --------------------------------------

    def hardcoded_pos_fixes(self) -> None:
        """Apply verified per-token POS corrections from 2017."""
        for f in self.targets["pos_fixes"]:
            sid, wid = f["sid"], f["wid"]
            cur = self.word_at(sid, wid)
            if cur and cur[0] == f["word"]:
                if cur[1] != f["new_pos"]:
                    self.set_pos(sid, wid, f["new_pos"], "hardcoded")
                continue
            # surface moved: look for a unique (word, old pos) match
            cands = self.conn.execute(
                "SELECT wid FROM word WHERE sid = ? AND word = ? AND pos = ?",
                (sid, f["word"], f["old_pos"])).fetchall()
            if len(cands) == 1:
                self.set_pos(sid, cands[0][0], f["new_pos"], "hardcoded")
                self.note(f"relocated pos fix sid={sid} wid={wid}->"
                          f"{cands[0][0]} {f['word']!r} -> {f['new_pos']}")
            else:
                self.note(f"SKIP pos fix sid={sid} wid={wid} expected "
                          f"{f['word']!r}, found {cur!r}")

    # -- phase 4: VAX ------------------------------------------------------

    def vax_fixes(self) -> None:
        """Rewrite auxiliary VAX tags (fixpunct Task 1.5)."""
        u = self.mark_and_update
        u("UPDATE word SET pos = 'MD' WHERE word = '''ll' "
          "AND pos IN ('VBD', 'VAX', 'RB')")
        u("UPDATE word SET pos = 'RB' WHERE word IN ('not', 'just') "
          "AND pos = 'VAX'")
        u("UPDATE word SET pos = 'MD' WHERE word = 'SHALL' AND pos = 'VAX'")
        # 2017 also demoted every 'just'/JJ to RB; log them for review
        for sid, wid in self.conn.execute(
                "SELECT sid, wid FROM word WHERE word = 'just' "
                "AND pos = 'JJ'").fetchall():
            self.note(f"just/JJ -> RB at sid={sid} wid={wid}")
            self.set_pos(sid, wid, "RB", "vax")
        for sid, wid, word in self.conn.execute(
                "SELECT sid, wid, word FROM word WHERE pos = 'VAX'").fetchall():
            base = VAX_POS.get(word)
            if base is None:
                self.note(f"SKIP unknown VAX word sid={sid} wid={wid} {word!r}")
                continue
            self.set_pos(sid, wid, base + "-VAX", "vax")

    # -- phase 5: token splits ---------------------------------------------

    def split_word(self, sid: int, wid: int,
                   parts: list[tuple[str, str, str]]) -> None:
        """Replace one token with several, relinking concepts to all parts.

        Args:
            sid: Sentence id.
            wid: Position of the token to replace.
            parts: (word, pos, lemma) triples for the replacement tokens.
        """
        links = self.conn.execute(
            "SELECT cid FROM cwl WHERE sid = ? AND wid = ?",
            (sid, wid)).fetchall()
        self.shift_wids(sid, wid, len(parts) - 1)
        self.conn.execute(
            "DELETE FROM word WHERE sid = ? AND wid = ?", (sid, wid))
        for i, (word, pos, lemma) in enumerate(parts):
            self.conn.execute(
                "INSERT INTO word (sid, wid, word, pos, lemma) "
                "VALUES (?, ?, ?, ?, ?)", (sid, wid + i, word, pos, lemma))
        for (cid,) in links:
            # the original link survives at the first part; add the rest
            for i in range(1, len(parts)):
                self.conn.execute(
                    "INSERT OR IGNORE INTO cwl (sid, wid, cid, usrname) "
                    "VALUES (?, ?, ?, 'fix_eng_pos')", (sid, wid + i, cid))
        self.counts["split"] += 1
        self.modified_sids.add(sid)

    def _measure_parts(self, token: str) -> list[tuple[str, str, str]] | None:
        """Derive split parts for a Zm/Zp/Zu measure token.

        Returns None when the token shape is not understood.
        """
        raw = token.split("_")
        # 'Hong Kong dollars' / 'Canadian dollars' keep the currency as MWE
        if len(raw) >= 3 and raw[-2] == "Kong":
            raw = raw[:-3] + ["_".join(raw[-3:])]
        elif len(raw) >= 2 and raw[-2] == "Canadian":
            raw = raw[:-2] + ["_".join(raw[-2:])]
        parts: list[tuple[str, str, str]] = []
        for i, p in enumerate(raw):
            last = i == len(raw) - 1
            if p in ("a", "an", "A", "An"):
                parts.append((p, "DT", p.lower()))
            elif p.startswith("Hong_Kong"):
                parts.append((p, "NNPS", "Hong_Kong_dollar"))
            elif p.startswith("Canadian"):
                parts.append((p, "NNPS", "Canadian_dollar"))
            elif last:
                if p not in UNIT_POS:
                    return None
                pos, lemma = UNIT_POS[p]
                parts.append((p, pos, lemma))
            elif re.fullmatch(r"[0-9][0-9.,]*(-?(million|billion))?", p) or \
                    p.lower() in NUMBER_WORDS or p in ("million", "billion"):
                parts.append((p, "CD", p))
            else:
                return None
        return parts if len(parts) >= 2 else None

    def token_splits(self) -> None:
        """Split Zm/Zp/Zu measures, GBP amounts; merge S + $ (fixpunct)."""
        # 'a' wrongly tagged Zp in two Sherlock sentences
        self.mark_and_update(
            "UPDATE word SET pos = 'DT' WHERE word = 'a' AND pos = 'Zp' "
            "AND sid IN (11358, 11370)")
        for sid, wid, word, pos in self.conn.execute(
                "SELECT sid, wid, word, pos FROM word "
                "WHERE pos IN ('Zm', 'Zp', 'Zu') "
                "ORDER BY sid, wid DESC").fetchall():
            parts = self._measure_parts(word)
            if parts is None:
                self.note(f"SKIP unparsed {pos} token sid={sid} wid={wid} "
                          f"{word!r}")
                continue
            self.split_word(sid, wid, parts)
        # GBP: £420 -> £ + 420
        for sid, wid, word in self.conn.execute(
                "SELECT sid, wid, word FROM word WHERE word GLOB '£[0-9]*' "
                "ORDER BY sid, wid DESC").fetchall():
            amount = word[1:]
            self.split_word(sid, wid, [
                ("£", "SYM", "£"), (amount, "CD", amount)])
        # Singapore dollars: S + $ -> S$
        for sid, wid in self.conn.execute(
                "SELECT sid, wid FROM word WHERE word = '$' "
                "ORDER BY sid, wid DESC").fetchall():
            prev = self.word_at(sid, wid - 1)
            if not prev or prev[0] != "S":
                self.note(f"SKIP $ merge sid={sid} wid={wid}: previous "
                          f"token is {prev!r}, not 'S'")
                continue
            self.conn.execute(
                "UPDATE word SET word = 'S$', pos = 'SYM', lemma = '$_sgd' "
                "WHERE sid = ? AND wid = ?", (sid, wid - 1))
            # move any concept links from '$' to the merged token, then
            # close the gap (unlike 2017, tagged concepts are kept)
            self.conn.execute(
                "UPDATE OR IGNORE cwl SET wid = ? WHERE sid = ? AND wid = ?",
                (wid - 1, sid, wid))
            self.conn.execute(
                "UPDATE concept SET clemma = 'S$' WHERE sid = ? AND cid IN "
                "(SELECT cid FROM cwl WHERE sid = ? AND wid = ?)",
                (sid, sid, wid - 1))
            self.conn.execute(
                "DELETE FROM word WHERE sid = ? AND wid = ?", (sid, wid))
            self.shift_wids(sid, wid, -1)
            # the amount that moves up next to S$ is a number (2017: CD)
            moved = self.word_at(sid, wid)
            if moved and re.match(r"[0-9]", moved[0]) and moved[1] != "CD":
                self.set_pos(sid, wid, "CD", "split")
            self.counts["split"] += 1
            self.modified_sids.add(sid)

    # -- phase 6: token rewrites (Sherlock hand fixes) -----------------------

    def token_rewrites(self) -> None:
        """Replay 2017 hand-fixed tokenisation where still applicable."""
        for sid_s, tr in self.targets["token_rewrites"].items():
            sid = int(sid_s)
            cur = [list(r) for r in self.sent_words(sid)]
            orig = [list(r) for r in tr["orig"]]
            final = [list(r) for r in tr["final"]]
            cur_surf = [(r[0], r[1]) for r in cur]
            if cur_surf == [(r[0], r[1]) for r in final]:
                continue
            # compare surfaces only: earlier phases already retag POS
            if cur_surf != [(r[0], r[1]) for r in orig]:
                self.note(f"SKIP token rewrite sid={sid}: sentence has "
                          "diverged from the 2017 state")
                continue
            # surviving tokens keep their current pos/lemma; tokens the
            # 2017 fix introduced take their 2017 pos/lemma
            cur_by_wid = {r[0]: r for r in cur}
            # remap concept links through the surface alignment
            olds = [r[1] for r in orig]
            news = [r[1] for r in final]
            sm = difflib.SequenceMatcher(a=olds, b=news, autojunk=False)
            mapping: dict[int, int] = {}
            for a, b, size in sm.get_matching_blocks():
                for k in range(size):
                    mapping[orig[a + k][0]] = final[b + k][0]
            links = self.conn.execute(
                "SELECT wid, cid, COALESCE(usrname, '') FROM cwl "
                "WHERE sid = ?", (sid,)).fetchall()
            for wid, cid, _usr in links:
                if wid not in mapping:
                    self.note(f"WARN token rewrite sid={sid}: cwl link at "
                              f"removed wid={wid} (cid={cid}) dropped")
            self.conn.execute("DELETE FROM cwl WHERE sid = ?", (sid,))
            self.conn.execute("DELETE FROM word WHERE sid = ?", (sid,))
            back = {fw: ow for ow, fw in mapping.items()}
            for wid, word, pos, lemma in final:
                if wid in back:
                    _, _, pos, lemma = cur_by_wid[back[wid]]
                self.conn.execute(
                    "INSERT INTO word (sid, wid, word, pos, lemma) "
                    "VALUES (?, ?, ?, ?, ?)", (sid, wid, word, pos, lemma))
            for wid, cid, usr in links:
                if wid in mapping:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO cwl (sid, wid, cid, usrname) "
                        "VALUES (?, ?, ?, ?)",
                        (sid, mapping[wid], cid, usr or None))
            self.counts["rewrite"] += 1
            self.modified_sids.add(sid)

    # -- phases 7/8: text fixes ---------------------------------------------

    def sent_fixes(self) -> None:
        """Correct sentence text (typos, control characters)."""
        for f in self.targets["sent_fixes"]:
            row = self.conn.execute(
                "SELECT sent FROM sent WHERE sid = ?", (f["sid"],)).fetchone()
            if row is None or row[0] == f["new"]:
                continue
            if row[0] != f["orig"]:
                self.note(f"SKIP sent fix sid={f['sid']}: text has diverged")
                continue
            self.upd("UPDATE sent SET sent = ? WHERE sid = ?",
                     (f["new"], f["sid"]), "sent")
            self.modified_sids.add(f["sid"])

    def word_fixes(self) -> None:
        """Correct individual word surfaces/lemmas/POS (typos)."""
        applied_surface: dict[tuple[int, int], str] = {}
        for f in self.targets["word_fixes"]:
            key = (f["sid"], f["wid"])
            row = self.conn.execute(
                f"SELECT word, {f['field']} FROM word WHERE sid = ? AND wid = ?",
                key).fetchone()
            if row is None:
                self.note(f"SKIP word fix sid={f['sid']} wid={f['wid']}: gone")
                continue
            if row[1] == f["new"]:
                continue
            expected = applied_surface.get(key, f["word"])
            if row[0] != expected:
                self.note(f"SKIP word fix sid={f['sid']} wid={f['wid']}: "
                          f"expected {expected!r}, found {row[0]!r}")
                continue
            if f["field"] == "word":
                applied_surface[key] = f["new"]
            self.upd(f"UPDATE word SET {f['field']} = ? "
                     "WHERE sid = ? AND wid = ?",
                     (f["new"], f["sid"], f["wid"]), "wordfix")
            self.modified_sids.add(f["sid"])

    # -- phase 9: consistency ------------------------------------------------

    @staticmethod
    def tokens_match_sent(sent: str, words: list[str]) -> bool:
        """Check the concatenated tokens reproduce the sentence text."""
        fixed = "".join(
            w.replace("``", '"').replace("''", '"').replace("_", "")
            .replace(" ", "") for w in words)
        return fixed == sent.replace(" ", "")

    def consistency_repair(self) -> list[int]:
        """Repair tokenisation/text mismatches; return still-broken sids.

        Port of task3consistency's generic fixsent: tab and control
        characters in the text, straight/curly apostrophe contractions.
        """
        broken: list[int] = []
        for sid, sent in self.conn.execute(
                "SELECT sid, sent FROM sent").fetchall():
            words = [w for (w,) in self.conn.execute(
                "SELECT word FROM word WHERE sid = ? ORDER BY wid", (sid,))]
            if not sent or not words:
                continue
            if self.tokens_match_sent(sent, words):
                continue
            if "\t" in sent or "\x0b" in sent:
                self.upd("UPDATE sent SET sent = ? WHERE sid = ?",
                         (sent.replace("\t", " ").replace("\x0b", " "), sid),
                         "consist")
                self.modified_sids.add(sid)
            elif self._fix_contraction(sid, sent, words):
                self.modified_sids.add(sid)
            words = [w for (w,) in self.conn.execute(
                "SELECT word FROM word WHERE sid = ? ORDER BY wid", (sid,))]
            sent = self.conn.execute(
                "SELECT sent FROM sent WHERE sid = ?", (sid,)).fetchone()[0]
            if not self.tokens_match_sent(sent, words):
                broken.append(sid)
        return broken

    def _fix_contraction(self, sid: int, sent: str,
                         words: list[str]) -> bool:
        """Repair not/n't and curly-quote token mismatches for one sid."""
        for form, base in STRAIGHT_NOT.items():
            if form in sent and base in words and "not" in words:
                idx = words.index(base)
                if idx + 1 < len(words) and words[idx + 1] == "not":
                    self.upd("UPDATE word SET word = 'n''t' "
                             "WHERE sid = ? AND wid = "
                             "(SELECT wid FROM word WHERE sid = ? "
                             " ORDER BY wid LIMIT 1 OFFSET ?)",
                             (sid, sid, idx + 1), "consist")
                    return True
        for curly_form, straight in CURLY.items():
            if curly_form in sent and straight in words:
                self.upd("UPDATE word SET word = ? WHERE sid = ? AND word = ?",
                         (curly_form, sid, straight), "consist")
                return True
        for form, base in CURLY_NOT.items():
            if form in sent and base in words and "not" in words:
                self.upd("UPDATE word SET word = 'n’t' "
                         "WHERE sid = ? AND word = 'not'", (sid,), "consist")
                return True
        if "’s" in sent and "'s" in words and "'s" not in sent:
            self.upd("UPDATE word SET word = '’s' "
                     "WHERE sid = ? AND word = '''s'", (sid,), "consist")
            return True
        if "'s" in sent and "’s" in words and "’s" not in sent:
            self.upd("UPDATE word SET word = '''s' "
                     "WHERE sid = ? AND word = '’s'", (sid,), "consist")
            return True
        return False

    # -- phase 10: clemma/lemma capitalisation --------------------------------

    def clemma_case_sync(self) -> None:
        """Synchronise clemma and lemma capitalisation (fixclem port).

        Only touches concepts where clemma and the joined word lemmas are
        equal ignoring case and spacing, so nothing but capitalisation
        can change.  Also fixes the 'doe'->'does' lemmatiser error and
        lemmatises 'm / 're to 'be' when the concept says so.
        """
        joined = self.conn.execute(
            """SELECT c.sid, c.cid, c.clemma, w.wid, w.lemma
               FROM concept c
               JOIN cwl l ON l.sid = c.sid AND l.cid = c.cid
               JOIN word w ON w.sid = l.sid AND w.wid = l.wid
               ORDER BY c.sid, c.cid, w.wid""").fetchall()
        grouped: dict[tuple[int, int], list[tuple[int, str]]] = {}
        clemma_of: dict[tuple[int, int], str] = {}
        for sid, cid, clemma, wid, lemma in joined:
            grouped.setdefault((sid, cid), []).append((wid, lemma or ""))
            clemma_of[(sid, cid)] = clemma
        for (sid, cid), pairs in grouped.items():
            clemma = clemma_of[(sid, cid)]
            if clemma is None:
                continue
            lemmas = " ".join(lem for _, lem in pairs)
            clem_parts = str(clemma).split()
            lem_parts = [lem for _, lem in pairs]
            wid_list = [wid for wid, _ in pairs]
            if len(clem_parts) != len(lem_parts):
                # special lemmatiser errors handled regardless of shape
                if clemma == "be" and lemmas in ("'m", "'re"):
                    self.upd("UPDATE word SET lemma = 'be' "
                             "WHERE sid = ? AND wid = ?",
                             (sid, wid_list[0]), "clemma")
                continue
            if clemma.replace(" ", "") == lemmas.replace(" ", ""):
                continue
            for i, (cp, lp) in enumerate(zip(clem_parts, lem_parts)):
                if cp == lp:
                    continue
                if lp == "doe" and cp == "does":
                    self.upd("UPDATE word SET lemma = 'does' "
                             "WHERE sid = ? AND wid = ?",
                             (sid, wid_list[i]), "clemma")
                elif cp.lower() == lp.lower():
                    # capitalisation mismatch: prefer the capitalised form
                    fixed = cp if cp[:1].isupper() else lp
                    if cp != fixed:
                        clem_parts[i] = fixed
                        self.upd("UPDATE concept SET clemma = ? "
                                 "WHERE sid = ? AND cid = ?",
                                 (" ".join(clem_parts), sid, cid), "clemma")
                    if lp != fixed:
                        self.upd("UPDATE word SET lemma = ? "
                                 "WHERE sid = ? AND wid = ?",
                                 (fixed, sid, wid_list[i]), "clemma")

    # -- phase 11: offsets -----------------------------------------------------

    def refresh_offsets(self) -> None:
        """Recompute cfrom/cto for every modified sentence."""
        n = 0
        for sid in sorted(self.modified_sids):
            row = self.conn.execute(
                "SELECT sent FROM sent WHERE sid = ?", (sid,)).fetchone()
            if not row or not row[0]:
                continue
            words = self.conn.execute(
                "SELECT wid, word FROM word WHERE sid = ? ORDER BY wid",
                (sid,)).fetchall()
            offsets = find_word_offsets(row[0], [w for _, w in words])
            for (wid, _), off in zip(words, offsets):
                cfrom, cto = off if off else (None, None)
                self.conn.execute(
                    "UPDATE word SET cfrom = ?, cto = ? "
                    "WHERE sid = ? AND wid = ?", (cfrom, cto, sid, wid))
                n += 1
        self.counts["offsets"] = n

    # -- verification -----------------------------------------------------------

    def verify(self) -> dict:
        """Integrity checks and residual-tag census after fixing."""
        res: dict = {}
        res["residual_tags"] = self.conn.execute(
            "SELECT pos, COUNT(*) FROM word WHERE pos NOT IN ({}) "
            "AND pos NOT LIKE '%-VAX' GROUP BY pos ORDER BY 2 DESC".format(
                ",".join("?" * len(PENN_TAGS))),
            tuple(PENN_TAGS)).fetchall()
        res["dup_wid"] = self.conn.execute(
            "SELECT COUNT(*) FROM (SELECT sid, wid FROM word "
            "GROUP BY sid, wid HAVING COUNT(*) > 1)").fetchone()[0]
        res["cwl_no_word"] = self.conn.execute(
            "SELECT COUNT(*) FROM cwl WHERE NOT EXISTS (SELECT 1 FROM word "
            "WHERE word.sid = cwl.sid AND word.wid = cwl.wid)").fetchone()[0]
        res["cwl_no_concept"] = self.conn.execute(
            "SELECT COUNT(*) FROM cwl WHERE NOT EXISTS (SELECT 1 FROM concept "
            "WHERE concept.sid = cwl.sid AND concept.cid = cwl.cid)"
        ).fetchone()[0]
        return res


def run(db_path: Path, dry_run: bool, report_path: Path) -> int:
    """Run the full pipeline against one database.

    Args:
        db_path: Corpus database to fix.
        dry_run: Roll back instead of committing.
        report_path: Where to write the detailed skip/warning report.

    Returns:
        Process exit code (0 on success, 1 on integrity failure).
    """
    with open(TARGETS_FILE, encoding="utf-8") as fh:
        targets = json.load(fh)
    conn = sqlite3.connect(db_path)
    # foreign keys stay off: the legacy schema declares an ewl->word
    # reference without a matching unique index, so enabling enforcement
    # makes every wid renumbering fail with "foreign key mismatch"
    fixer = Fixer(conn, targets)

    before = dict(conn.execute(
        "SELECT 'word', COUNT(*) FROM word UNION ALL "
        "SELECT 'concept', COUNT(*) FROM concept UNION ALL "
        "SELECT 'cwl', COUNT(*) FROM cwl UNION ALL "
        "SELECT 'sent', COUNT(*) FROM sent").fetchall())

    logger.info("Phase 1: pattern POS fixes")
    fixer.pattern_pos_fixes()
    logger.info("Phase 2: quote fixes")
    fixer.quote_fixes()
    logger.info("Phase 3: hardcoded POS fixes")
    fixer.hardcoded_pos_fixes()
    fixer.pattern_residual_fixes()
    logger.info("Phase 4: VAX fixes")
    fixer.vax_fixes()
    logger.info("Phase 5: token splits")
    fixer.token_splits()
    logger.info("Phase 6: token rewrites")
    fixer.token_rewrites()
    logger.info("Phase 7: sentence text fixes")
    fixer.sent_fixes()
    logger.info("Phase 8: word text fixes")
    fixer.word_fixes()
    logger.info("Phase 9: consistency repair")
    broken = fixer.consistency_repair()
    logger.info("Phase 10: clemma/lemma capitalisation")
    fixer.clemma_case_sync()
    logger.info("Phase 11: refresh offsets for %d modified sentences",
                len(fixer.modified_sids))
    fixer.refresh_offsets()

    after = dict(conn.execute(
        "SELECT 'word', COUNT(*) FROM word UNION ALL "
        "SELECT 'concept', COUNT(*) FROM concept UNION ALL "
        "SELECT 'cwl', COUNT(*) FROM cwl UNION ALL "
        "SELECT 'sent', COUNT(*) FROM sent").fetchall())
    checks = fixer.verify()

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(f"fix_eng_pos report for {db_path}\n\n")
        fh.write(f"counts: {dict(fixer.counts)}\n")
        fh.write(f"rows before: {before}\nrows after:  {after}\n")
        fh.write(f"integrity: {checks['dup_wid']} duplicate wids, "
                 f"{checks['cwl_no_word']} cwl without word, "
                 f"{checks['cwl_no_concept']} cwl without concept\n")
        fh.write("residual non-Penn tags:\n")
        for pos, n in checks["residual_tags"]:
            fh.write(f"  {pos!r}: {n}\n")
        fh.write(f"\ntokenisation still inconsistent: {len(broken)} "
                 f"sentences\n  {broken[:50]}\n\n")
        fh.write("\n".join(fixer.report) + "\n")
    logger.info("Report written to %s", report_path)
    logger.info("Summary: %s", dict(fixer.counts))
    logger.info("Residual non-Penn tags: %s",
                checks["residual_tags"][:12])

    ok = (checks["dup_wid"] == 0 and checks["cwl_no_word"] == 0)
    if dry_run:
        conn.rollback()
        logger.info("Dry run: rolled back.")
    elif ok:
        conn.commit()
        logger.info("Committed.")
    else:
        conn.rollback()
        logger.error("Integrity check failed; rolled back.")
    conn.close()
    return 0 if ok else 1


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Apply the 2017-11-17 English POS/tokenisation fixes.")
    parser.add_argument("db", type=Path, help="Path to eng.db")
    parser.add_argument("--dry-run", action="store_true",
                        help="Apply, verify, then roll back")
    parser.add_argument("--report", type=Path,
                        default=Path("build/log/fix_eng_pos.txt"),
                        help="Detailed report file")
    args = parser.parse_args()
    if not args.db.exists():
        logger.error("Database not found: %s", args.db)
        sys.exit(1)
    sys.exit(run(args.db, args.dry_run, args.report))


if __name__ == "__main__":
    main()
