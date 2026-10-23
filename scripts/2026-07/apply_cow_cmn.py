#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["openpyxl"]
# ///
"""Apply Jia Qi Yeo's Chinese wordnet edits (COW spreadsheet) to wn-ntumc.db.

Input: data/COW Definitions (Jia Qi).xlsx, four sheets (cmn_edu,
ntumc_intersect_core, rest_of_core, tufs_lexicon) of synsets with
Chinese definitions, optional "easy" definitions, lemmas to add and
lemmas to delete, and free-text notes.

What is applied, per synset:
  * one Chinese definition.  Where a synset is on two sheets (always
    cmn_edu and tufs_lexicon), cmn_edu wins (natural Chinese, Chinese
    punctuation) except in TUFS_WINS, where the cmn_edu text is wrong.
    Where an easy definition is clearly better (EASY_WINS), it is used
    instead.  Existing Chinese definitions that differ are replaced.
  * lemmas to delete: senses removed (matching X的 as X+的 too).
  * lemmas to add: senses added, with a new word if needed.
Changes are made with triggers on, so they are logged (usr 'jiaqi').

Everything not applied goes to docs/cow-cmn-review.tsv (written by the
first run only, since replaced definitions vanish after it): the losing
definition of each pair, unused easy definitions, replaced old
definitions, deletions that matched nothing, notes, suggested English
definitions, and synsets not in the wordnet.  Nothing is deleted
beyond the listed lemmas; no synsets are deleted.

Usage:
    scripts/2026-07/apply_cow_cmn.py WN_DB --dry-run
    scripts/2026-07/apply_cow_cmn.py WN_DB --fix
"""

import argparse
import csv
import logging
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
XLSX = ROOT / "data" / "COW Definitions (Jia Qi).xlsx"
REVIEW = ROOT / "docs" / "cow-cmn-review.tsv"
USR, SRC, LANG = "jiaqi", "cow", "cmn"
SEP = re.compile(r"[;；、]")

# cmn_edu definition is wrong or misleading; use tufs_lexicon
TUFS_WINS = {
    "77000090-n",  # manner: 礼貌性 'politeness'
    "01247240-a",  # hot: 使用热能 'uses heat energy'
    "07575076-n",  # lunch: 中餐 also 'Chinese food'
    "07575726-n",  # dinner: 午后 'afternoon', not midday
    "00729108-n",  # homework: 备课 'lesson preparation' (teachers)
    "09853467-n",  # older brother: 年长的兄长 is circular
    "09854218-n",  # older sister: 年纪比自己大的女子 omits sibling
    "01048762-a",  # resulting favorably: noun phrase 效果
    "07557434-n",  # dish: 经烹调的食物 is food in general
    "08559508-n",  # residence: omits 'at a particular time'
    "00027918-r",  # so far: omits 'up to now'
}

# easy definition is clearer or more accurate than the full one
EASY_WINS = {
    "10368009-n",  # nun: 出家的女子
    "03365991-n",  # floor/storey: 楼房的一层
    "02604760-v",  # be (quality): 联系两种事物，表示特征
    "00690058-a",  # deep: 从上到下或外到内的距离大
    "01433493-a",  # long: 两端之间的距离相当大
    "05821486-n",  # precedent: 供参照的以前的事例
    "00429048-n",  # diversion: 快乐有趣的活动
    "01212519-n",  # support: 赞成并全力支持
    "01854129-a",  # auxiliary: 从旁帮助
}

# synsets renamed by fixwn.py (RENAME_SYNSET) that the sheet uses by old ID
RENAMED = {"80001711-z": "80001711-x"}  # 们, plural suffix

# lemmas to delete as written in the sheet -> as found in the wordnet
DELETE_ALIASES = {
    ("00251013-n", "洗清罪恶等"): "洗清[罪恶等",
    ("00251013-n", "洗清 罪恶 等"): "洗清 [ 罪恶 等",
    ("00987071-v", "制定"): "制订",
    ("07840804-n", "蛋鸟"): "蛋鸡",
    ("07965817-n", "某 一 部分特定 的 人"): "某 一 部分 特定 的 人",
}


@dataclass
class Row:
    """One spreadsheet row."""

    sheet: str
    synset: str
    english: str
    definition: str
    easy: str
    add: list[str] = field(default_factory=list)
    delete: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def split(cell: object) -> list[str]:
    """Split a lemma cell on ; ； or 、 and drop empty items."""
    if cell is None:
        return []
    return [x.strip() for x in SEP.split(str(cell)) if x.strip()]


def text(cell: object) -> str:
    """Return a cell as stripped text ('' for empty)."""
    return str(cell).strip() if cell is not None else ""


def read_rows(path: Path) -> list[Row]:
    """Read all edit rows from the spreadsheet (skipping 'All Synsets')."""
    import openpyxl  # only needed here; keeps the module importable in tests

    wb = openpyxl.load_workbook(path, read_only=True)
    rows = []
    for ws in wb.worksheets:
        if ws.title == "All Synsets":
            continue
        it = ws.iter_rows(values_only=True)
        hdr = [text(h) for h in next(it)]
        # unlabelled column after the last header
        extra = max(i for i, h in enumerate(hdr) if h) + 1
        for r in it:
            if not r or not r[0]:
                continue
            g = dict(zip(hdr, r))
            notes = [text(g.get("Notes"))] if text(g.get("Notes")) else []
            # unlabelled column: suggested English definitions and comments
            if extra < len(r) and text(r[extra]):
                notes.append("extra column: " + text(r[extra]))
            rows.append(Row(ws.title, text(r[0]), text(g.get("English Definition")),
                            text(g.get("Chinese Definition")),
                            text(g.get("(opt) Easy Chinese Definition")),
                            split(g.get("Chinese Lemmas to ADD")),
                            split(g.get("Chinese Lemmas to DELETE")), notes))
    return rows


def choose(rows: list[Row]) -> tuple[str, list[tuple[Row, str, str]]]:
    """Pick the definition for one synset.

    Args:
        rows: The synset's rows from all sheets.

    Returns:
        (definition to use, [(row, kind, text) for the review file])
    """
    ss = rows[0].synset
    win = rows[0]
    if len(rows) > 1:
        pick = "tufs_lexicon" if ss in TUFS_WINS else "cmn_edu"
        win = next((r for r in rows if r.sheet == pick), rows[0])
    review = [(r, "alt_def", r.definition) for r in rows
              if r is not win and r.definition and r.definition != win.definition]
    chosen = win.definition
    if win.easy and ss in EASY_WINS:
        review.append((win, "full_def_replaced_by_easy", win.definition))
        chosen = win.easy
    review += [(r, "easy_def", r.easy) for r in rows
               if r.easy and not (r is win and ss in EASY_WINS)]
    return chosen, review


def lemma_forms(lemma: str) -> list[str]:
    """Forms a lemma to delete may have in the wordnet (X的 is X+的)."""
    forms = [lemma]
    if lemma.endswith("的") and not lemma.endswith("+的"):
        forms.append(lemma[:-1] + "+的")
    return forms


class Applier:
    """Apply the spreadsheet edits to one wn-ntumc.db connection."""

    def __init__(self, conn: sqlite3.Connection, dry_run: bool) -> None:
        """Wrap a connection; with dry_run, only count what would change."""
        self.conn = conn
        self.dry_run = dry_run
        self.counts: Counter = Counter()

    def _write(self, sql: str, args: tuple) -> sqlite3.Cursor | None:
        """Execute a write unless this is a dry run."""
        return None if self.dry_run else self.conn.execute(sql, args)

    def set_definition(self, ss: str, definition: str) -> list[str]:
        """Make definition the synset's only Chinese one; return replaced defs."""
        old = [d for (d,) in self.conn.execute(
            "SELECT def FROM synset_def WHERE synset=? AND lang=?", (ss, LANG))]
        if old == [definition]:
            self.counts["def already present"] += 1
            return []
        replaced = [d for d in old if d != definition]
        for d in replaced:
            self._write("DELETE FROM synset_def WHERE synset=? AND lang=? "
                        "AND def=?", (ss, LANG, d))
        if definition not in old:
            sid = self.conn.execute(
                "SELECT COALESCE(MAX(sid) + 1, 0) FROM synset_def "
                "WHERE synset=? AND lang=?", (ss, LANG)).fetchone()[0]
            self._write("INSERT INTO synset_def (synset, lang, def, sid, usr) "
                        "VALUES (?, ?, ?, ?, ?)", (ss, LANG, definition, sid, USR))
        self.counts["def replaced" if replaced else "def added"] += 1
        return replaced

    def delete_lemma(self, ss: str, lemma: str) -> bool:
        """Delete the synset's sense(s) for lemma; False if none matched."""
        lemma = DELETE_ALIASES.get((ss, lemma), lemma)
        wids = [w for f in lemma_forms(lemma) for (w,) in self.conn.execute(
            "SELECT s.wordid FROM sense s JOIN word w USING (wordid) "
            "WHERE s.synset=? AND w.lang=? AND w.lemma=?", (ss, LANG, f))]
        for w in wids:
            self._write("DELETE FROM sense WHERE synset=? AND wordid=?", (ss, w))
        if wids:
            self.counts["sense deleted"] += 1
            return True
        if self._was_deleted(ss, lemma):
            self.counts["sense already deleted"] += 1
            return True
        self.counts["delete not matched"] += 1
        return False

    def _was_deleted(self, ss: str, lemma: str) -> bool:
        """True if sense_log records this lemma's sense being deleted."""
        forms = lemma_forms(lemma)
        try:
            return bool(self.conn.execute(
                "SELECT 1 FROM sense_log l JOIN word w ON w.wordid = l.wordid_old "
                "WHERE l.synset_old=? AND l.synset_new IS NULL AND w.lang=? "
                f"AND w.lemma IN ({','.join('?' * len(forms))})",
                (ss, LANG, *forms)).fetchone())
        except sqlite3.OperationalError:  # copy without log tables
            return False

    def add_lemma(self, ss: str, lemma: str) -> None:
        """Add a sense of lemma to the synset, creating the word if needed."""
        if self.conn.execute(
                "SELECT 1 FROM sense s JOIN word w USING (wordid) "
                "WHERE s.synset=? AND w.lang=? AND w.lemma=?",
                (ss, LANG, lemma)).fetchone():
            self.counts["sense already present"] += 1
            return
        pos = ss[-1]
        row = self.conn.execute(
            "SELECT wordid FROM word WHERE lang=? AND lemma=? AND pos=?",
            (LANG, lemma, pos)).fetchone()
        if row:
            wid = row[0]
        else:
            self.counts["word added"] += 1
            cur = self._write("INSERT INTO word (lang, lemma, pos, usr) "
                              "VALUES (?, ?, ?, ?)", (LANG, lemma, pos, USR))
            wid = cur.lastrowid if cur else None
        self._write("INSERT INTO sense (synset, wordid, lang, src, confidence, "
                    "usr) VALUES (?, ?, ?, ?, 1.0, ?)", (ss, wid, LANG, SRC, USR))
        self.counts["sense added"] += 1


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("db", help="wn-ntumc.db to change (the server copy)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true",
                       help="Report what would change, change nothing")
    group.add_argument("--fix", action="store_true", help="Apply the edits")
    args = parser.parse_args()

    by_ss: dict[str, list[Row]] = defaultdict(list)
    for r in read_rows(XLSX):
        r.synset = RENAMED.get(r.synset, r.synset)
        by_ss[r.synset].append(r)

    conn = sqlite3.connect(args.db)
    synsets = {s for (s,) in conn.execute("SELECT synset FROM synset")}
    app = Applier(conn, args.dry_run)
    review: list[tuple[Row, str, str]] = []
    for ss, rows in by_ss.items():
        if ss not in synsets:
            review.append((rows[0], "synset_not_in_wordnet", rows[0].definition))
            continue
        definition, rev = choose(rows)
        review += rev
        if definition:
            review += [(rows[0], "old_def_replaced", d)
                       for d in app.set_definition(ss, definition)]
        for r in rows:
            for lemma in r.delete:
                if not app.delete_lemma(ss, lemma):
                    review.append((r, "delete_not_matched", lemma))
            for lemma in r.add:
                app.add_lemma(ss, lemma)
            review += [(r, "note", n) for n in r.notes]
    if args.fix:
        conn.commit()
    conn.close()

    logger.info("%s: %s", "would change" if args.dry_run else "changed",
                dict(sorted(app.counts.items())))
    # replaced definitions are only seen on the first run, so keep the
    # review file from that run; delete it to regenerate
    if REVIEW.exists():
        logger.info("kept existing %s", REVIEW.relative_to(ROOT))
        return
    with open(REVIEW, "w", encoding="utf-8", newline="") as fh:
        out = csv.writer(fh, delimiter="\t", lineterminator="\n")
        out.writerow(["synset", "sheet", "kind", "text", "english_definition"])
        for r, kind, txt in sorted(review, key=lambda x: (x[0].synset, x[1])):
            out.writerow([r.synset, r.sheet, kind, txt, r.english])
    logger.info("review file %s: %s", REVIEW.relative_to(ROOT),
                dict(sorted(Counter(k for _, k, _ in review).items())))


if __name__ == "__main__":
    main()
