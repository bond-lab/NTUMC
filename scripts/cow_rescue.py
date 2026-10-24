"""Rescue Chinese senses from excluded sources for otherwise empty COW synsets.

COW leaves out senses that come only from automatic sources (BOW, SEW,
Wiktionary).  After the sense corrections, some COW synsets have a
definition but no senses, although the NTU-MC wordnet has candidate lemmas
for them from those sources.  This script

  candidates  writes the candidates in the triage format (all flagged), so
              that triage_review.py build/compare/final can review them
  adds        appends the candidates judged OK (and not malformed) to COW's
              corrections/senses.tsv as ``add`` rows

  cow_rescue.py candidates COW_XML --db build/wn-ntumc.db --en-data WN_DIR
  cow_rescue.py adds --db build/wn-ntumc.db
"""

import argparse
import sqlite3
from pathlib import Path

import triage_review as tr

HEAD = ["id", "synset", "word", "other_words_in_synset", "english_words",
        "english_definition", "own_definition"]


def display_form(lemma: str) -> str:
    """The written form a lemma gets in COW (+的/+地 lose the +)."""
    return lemma.replace("+的", "的").replace("+地", "地")


def db_candidates(db: Path, synsets: set[str], done: set[tuple[str, str]]) -> dict:
    """{cow synset id: {display form: database lemma}} from excluded sources."""
    con = sqlite3.connect(db)
    rows = con.execute(
        "SELECT s.synset, w.lemma, s.src FROM sense AS s JOIN word AS w ON s.wordid = w.wordid"
        " WHERE s.lang = 'cmn'").fetchall()
    cand: dict[str, dict[str, str]] = {}
    for ss, lemma, src in rows:
        sid = "cow-" + ss
        if sid in synsets and "cmn:mwe" not in (src or "") and (sid, lemma) not in done:
            cand.setdefault(sid, {})[display_form(lemma)] = lemma
    return cand


def corrected(path: Path) -> set[tuple[str, str]]:
    """(synset_id, lemma) pairs already in a corrections file."""
    return {(r["synset_id"], r["lemma"]) for r in tr.read_tsv(path)}


def candidates(a: argparse.Namespace) -> None:
    """Write build/rescue/cmn/batch001.tsv and an all-flagged suspects file."""
    import wn
    from wn import lmf

    wn.config.data_directory = str(a.en_data)
    en = wn.Wordnet("omw-en:2.0")
    lex = lmf.load(str(a.cow_xml), progress_handler=None)["lexicons"][0]
    empty = {ss["id"]: ss for ss in lex["synsets"] if not ss.get("members")}
    cand = db_candidates(a.db, set(empty), corrected(a.corrections))
    rows = []
    for sid, forms in sorted(cand.items()):
        ss = empty[sid]
        ew = ed = ""
        if ss.get("ili") and ss["ili"] != "in" and (e := en.synsets(ili=ss["ili"])):
            ew, ed = ", ".join(e[0].lemmas()), e[0].definition() or ""
        own = (ss.get("definitions") or [{}])[0].get("text", "")
        for form in sorted(forms):
            others = " ".join(f for f in sorted(forms) if f != form)
            rows.append([f"cmn001-{len(rows) + 1}", sid, form, others, ew, ed, own])
    d = a.out / "cmn"
    for lang in tr.LANGS:
        (a.out / lang).mkdir(parents=True, exist_ok=True)
    tr.write_tsv(d / "batch001.tsv", HEAD, rows)
    tr.write_tsv(d / "batch001-suspects.tsv", ["id", "word", "reason"],
                 [[r[0], r[2], "candidate"] for r in rows])
    print(len(cand), "synsets,", len(rows), "candidate senses")


def adds(a: argparse.Namespace) -> None:
    """Append add rows for candidates judged OK to the COW corrections."""
    final = tr.read_tsv(a.review / "cmn" / "final.tsv")
    old = tr.read_tsv(a.corrections)
    cand = db_candidates(a.db, {r["synset"] for r in final}, set())
    new = [[r["synset"], cand[r["synset"]][r["word"]], "add", "",
            f"rescued from excluded sources: {r['reason']}".rstrip(": "),
            "rescue: 2 blind opus" + (" (adjudicated)" if r["decided_by"] == "adjudication"
                                      else ""), a.date, ""]
           for r in final if r["final"] == "OK" and "FORM" not in r["note_both"].split()]
    keep = [[r[c] for c in tr.CORR_HEAD] for r in old if r["source"].split(":")[0] != "rescue"]
    tr.write_tsv(a.corrections, tr.CORR_HEAD, sorted(keep + new))
    print(f"{len(new)} add rows of {len(final)} candidates in "
          f"{len({r[0] for r in new})} synsets")


def main() -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("candidates", "adds"))
    ap.add_argument("cow_xml", type=Path, nargs="?", help="COW XML with corrections applied")
    ap.add_argument("--db", type=Path, default=Path("build/wn-ntumc.db"))
    ap.add_argument("--en-data", type=Path, help="wn data directory with omw-en:2.0")
    ap.add_argument("--corrections", type=Path, default=Path("../cow/corrections/senses.tsv"))
    ap.add_argument("--out", type=Path, default=Path("build/rescue"))
    ap.add_argument("--review", type=Path, default=Path("build/rescue-opus"))
    ap.add_argument("--date", default="2026-10-24")
    a = ap.parse_args()
    candidates(a) if a.step == "candidates" else adds(a)


if __name__ == "__main__":
    main()
