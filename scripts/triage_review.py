"""Blind Opus review of the senses flagged by the Haiku triage.

Two runs see the flagged senses under fresh random ids, shuffled
differently and without the Haiku reason; senses on which the runs
disagree (or are both UNSURE) go to adjudication with both reasons.

  build      write runN/batchNNN.tsv + runN/key.tsv for each language
  compare    write adjudicateNN.tsv + adjudicate-key.tsv from the two runs
  final      combine everything into final.tsv per language
  corrections  write corrections/senses.tsv for COW and Wordnet Bahasa
"""

import argparse
import csv
import glob
import html
import random
import re
from collections import Counter
from pathlib import Path

LANGS = ("cmn", "id", "zsm")
NOTE_TAGS = {"FORM", "MS", "ID"}
COLS = ["word", "other_words_in_synset", "english_words", "english_definition",
        "own_definition"]


def read_tsv(path: Path) -> list[dict]:
    """Rows of a tab-separated file with a header."""
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE))


def write_tsv(path: Path, header: list[str], rows: list[list]) -> None:
    """Write a tab-separated file with a header."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        t = csv.writer(fh, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_NONE,
                       escapechar="\\")
        t.writerow(header)
        t.writerows(rows)


def flagged(triage: Path, lang: str) -> list[dict]:
    """Triage rows flagged SUSPECT, with the Haiku reason added."""
    reason = {}
    for f in sorted(glob.glob(f"{triage}/{lang}/batch*-suspects.tsv")):
        for r in read_tsv(Path(f)):
            if r.get("id"):
                reason[r["id"]] = (r.get("reason") or "").strip()
    rows = []
    for f in sorted(glob.glob(f"{triage}/{lang}/batch[0-9][0-9][0-9].tsv")):
        for r in read_tsv(Path(f)):
            if r["id"] in reason:
                r["haiku"] = reason[r["id"]]
                rows.append(r)
    return rows


def build(triage: Path, out: Path, size: int, seed: int) -> None:
    """Write two blind, differently shuffled batch sets per language."""
    for lang in LANGS:
        rows = flagged(triage, lang)
        for run in (1, 2):
            d = out / lang / f"run{run}"
            d.mkdir(parents=True, exist_ok=True)
            rng = random.Random(seed * 10 + run + LANGS.index(lang) * 100)
            ids = rng.sample(range(100000, 999999), len(rows))
            order = list(zip(ids, rows))
            rng.shuffle(order)
            write_tsv(d / "key.tsv", ["id", "triage_id", "synset", "word"],
                      [[i, r["id"], r["synset"], r["word"]] for i, r in order])
            for b in range(0, len(order), size):
                write_tsv(d / f"batch{b // size + 1:03d}.tsv", ["id"] + COLS,
                          [[i] + [r[c] for c in COLS] for i, r in order[b:b + size]])
        print(lang, len(rows), "flagged ->", -(-len(rows) // size), "batches per run")


def verdicts(d: Path) -> dict:
    """triage_id -> (verdict, reason) for one run."""
    key = {r["id"]: r["triage_id"] for r in read_tsv(d / "key.tsv")}
    out = {}
    for f in sorted(glob.glob(f"{d}/batch[0-9][0-9][0-9]-review.tsv")):
        for r in read_tsv(Path(f)):
            if r.get("id") in key:
                out[key[r["id"]]] = ((r.get("verdict") or "").strip().upper(),
                                     (r.get("reason") or "").strip())
    return out


def notes(d: Path) -> dict:
    """triage_id -> set of form tags (FORM, MS, ID) given in one run."""
    key = {r["id"]: r["triage_id"] for r in read_tsv(d / "key.tsv")}
    out = {}
    for f in sorted(glob.glob(f"{d}/batch[0-9][0-9][0-9]-review.tsv")):
        for r in read_tsv(Path(f)):
            if r.get("id") in key:
                out[key[r["id"]]] = set((r.get("note") or "").upper().split()) & NOTE_TAGS
    return out


def compare(triage: Path, out: Path, size: int, seed: int) -> None:
    """Write adjudication batches for disagreements and double UNSURE."""
    for lang in LANGS:
        rows = {r["id"]: r for r in flagged(triage, lang)}
        r1, r2 = verdicts(out / lang / "run1"), verdicts(out / lang / "run2")
        pairs = Counter((r1.get(k, ("MISSING",))[0], r2.get(k, ("MISSING",))[0]) for k in rows)
        print(f"== {lang}: run1 rows x run2 cols")
        for a in ("OK", "WRONG", "UNSURE", "MISSING"):
            print(f"  {a:7}", {b: pairs[(a, b)] for b in ("OK", "WRONG", "UNSURE", "MISSING")})
        todo = [k for k in rows
                if r1.get(k, ("MISSING",))[0] != r2.get(k, ("MISSING",))[0]
                or r1.get(k, ("MISSING",))[0] not in ("OK", "WRONG")]
        rng = random.Random(seed + 7 + LANGS.index(lang))
        rng.shuffle(todo)
        ids = rng.sample(range(100000, 999999), len(todo))
        d = out / lang / "adjudicate"
        d.mkdir(parents=True, exist_ok=True)
        write_tsv(d / "key.tsv", ["id", "triage_id"], [[i, k] for i, k in zip(ids, todo)])
        for b in range(0, len(todo), size):
            write_tsv(d / f"batch{b // size + 1:03d}.tsv",
                      ["id"] + COLS + ["review_a", "reason_a", "review_b", "reason_b"],
                      [[i] + [rows[k][c] for c in COLS]
                       + list(r1.get(k, ("MISSING", ""))) + list(r2.get(k, ("MISSING", "")))
                       for i, k in zip(ids[b:b + size], todo[b:b + size])])
        print(f"  to adjudicate: {len(todo)} -> {-(-len(todo) // size)} batches")


def final(triage: Path, out: Path) -> None:
    """Combine triage, both runs and adjudication into final.tsv."""
    for lang in LANGS:
        rows = flagged(triage, lang)
        r1, r2 = verdicts(out / lang / "run1"), verdicts(out / lang / "run2")
        adj = verdicts(out / lang / "adjudicate") if (out / lang / "adjudicate").exists() else {}
        n1, n2 = notes(out / lang / "run1"), notes(out / lang / "run2")
        res, tab = [], Counter()
        for r in rows:
            k = r["id"]
            v1, v2 = r1.get(k, ("MISSING", "")), r2.get(k, ("MISSING", ""))
            if v1[0] == v2[0] and v1[0] in ("OK", "WRONG"):
                fin, by, why = v1[0], "both", v1[1] or v2[1]
            elif k in adj:
                fin, by, why = adj[k][0], "adjudication", adj[k][1]
            else:
                fin, by, why = "UNSURE", "none", ""
            act = {"WRONG": "remove", "OK": "keep"}.get(fin, "lower")
            tab[act] += 1
            a, b = n1.get(k, set()), n2.get(k, set())
            res.append([r["synset"], r["word"], r["haiku"], v1[0], v2[0], fin, act, by, why,
                        " ".join(sorted(a & b)), " ".join(sorted(a ^ b))])
        write_tsv(out / lang / "final.tsv",
                  ["synset", "word", "haiku_reason", "run1", "run2", "final", "action",
                   "decided_by", "reason", "note_both", "note_one"], res)
        print(lang, dict(tab))


# form notes that remove a sense in each language (agreed by both runs)
FORM_REMOVE = {"cmn": {"FORM"}, "id": {"FORM", "MS"}, "zsm": {"FORM", "ID"}}
FORM_LABEL = {"FORM": "malformed or not a word", "MS": "Malaysian, not Indonesian",
              "ID": "Indonesian, not Malaysian"}
CORR_HEAD = ["synset_id", "lemma", "action", "confidence", "reason", "source", "date",
             "new_lemma"]
CJK = r"[\u4e00-\u9fff\u3400-\u4dbf·]+"


def fixed_cmn(word: str) -> str | None:
    """Mechanical fix of a malformed Chinese lemma, or None.

    Drops a byte-order mark, converts traditional to simplified characters
    and joins Han characters separated by spaces; returns the result only if
    it differs and is all Han characters.
    """
    from opencc import OpenCC  # only needed for the cmn corrections

    new = OpenCC("t2s").convert(word.replace("\ufeff", ""))
    if re.fullmatch(rf"{CJK}(?: {CJK})+", new):
        new = new.replace(" ", "")
    return new if new != word and re.fullmatch(CJK, new) else None


def correction(lang: str, r: dict, date: str, have: set) -> list | None:
    """Correction row for one final.tsv row, or None to keep the sense.

    WRONG removes; a form note in FORM_REMOVE removes whatever the verdict,
    except that a Chinese lemma with a mechanical fix (fixed_cmn) whose
    meaning was not judged WRONG is renamed, unless the synset already has
    the fixed form (have: (synset_id, lemma) pairs); UNSURE (or undecided)
    lowers the confidence to 0.5.
    """
    forms = set(r["note_both"].split()) & FORM_REMOVE[lang]
    src = "triage: haiku + 2 blind opus" + (" (adjudicated)" if r["decided_by"] == "adjudication"
                                            else "")
    if lang == "cmn" and forms and r["final"] != "WRONG" and (new := fixed_cmn(r["word"])):
        if (r["synset"], new) not in have:
            return [r["synset"], r["word"], "rename", "", f"fixed form: {r['reason']}".rstrip(": "),
                    src + " + form note", date, new]
        return [r["synset"], r["word"], "remove", "", f"variant of {new}, which the synset has",
                src + " + form note", date]
    if forms:
        why = "; ".join(FORM_LABEL[f] for f in sorted(forms))
        return [r["synset"], r["word"], "remove", "", f"{why}: {r['reason']}".rstrip(": "),
                src + " + form note", date]
    if r["action"] == "remove":
        return [r["synset"], r["word"], "remove", "", r["reason"], src, date]
    if r["action"] == "lower":
        return [r["synset"], r["word"], "lower", "0.5", r["reason"], src, date]
    return None


# a sense in the wrong variety of Malay moves to the other Bahasa lexicon
MOVE = {"id": ("MS", "zsm"), "zsm": ("ID", "id")}


def release_senses(xml: Path, full: bool = False) -> set[tuple[str, str]]:
    """(synset offset, lemma) pairs of a released lexicon ((synset id, lemma) if full)."""
    have, lemma = set(), None
    with open(xml, encoding="utf-8") as fh:
        for line in fh:
            if m := re.search(r'<Lemma writtenForm="([^"]*)"', line):
                lemma = html.unescape(m.group(1))
            if m := re.search(r'<Sense [^>]*synset="([^"]*)"', line):
                have.add((m.group(1) if full else m.group(1).split("-", 2)[2], lemma))
    return have


def moves(lang: str, rows: list[dict], other: set, date: str) -> list[list]:
    """add rows for the other lexicon: right meaning, wrong variety, not there yet."""
    if lang not in MOVE:
        return []
    note, to = MOVE[lang]
    out = []
    for r in rows:
        off = r["synset"].split("-", 2)[2]
        if (note in r["note_both"].split() and r["final"] != "WRONG"
                and (off, r["word"]) not in other):
            out.append([f"wnb-{to}-{off}", r["word"], "add", "",
                        f"moved from wnb-{lang}: {FORM_LABEL[note]}",
                        "triage: haiku + 2 blind opus + form note", date])
    return out


def corrections(out: Path, targets: dict[str, Path], release: dict[str, Path],
                date: str) -> None:
    """Write corrections/senses.tsv files; targets maps a language to its file.

    release maps a language to its released XML, used to see which renamed
    or moved senses the lexicon already has.
    """
    by_file: dict[Path, list] = {}
    have = {lang: release_senses(release[lang]) for lang in ("id", "zsm")}
    cow = release_senses(release["cmn"], full=True)
    for lang in LANGS:
        final_rows = read_tsv(out / lang / "final.tsv")
        rows = [c + [""] * (len(CORR_HEAD) - len(c))
                for r in final_rows if (c := correction(lang, r, date, cow))]
        if lang in MOVE:
            rows += [c + [""] for c in moves(lang, final_rows, have[MOVE[lang][1]], date)]
        by_file.setdefault(targets[lang], []).extend(rows)
        tab = Counter(c[2] for c in rows)
        print(lang, dict(tab), "of which form notes",
              sum("form note" in c[5] and c[2] == "remove" for c in rows))
    for path, rows in by_file.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_tsv(path, CORR_HEAD, sorted(rows))
        print("wrote", path, len(rows))


def main() -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("build", "compare", "final", "corrections"))
    ap.add_argument("--triage", type=Path, default=Path("build/triage"))
    ap.add_argument("--out", type=Path, default=Path("build/triage-opus"))
    ap.add_argument("--size", type=int, default=150)
    ap.add_argument("--seed", type=int, default=20261024)
    ap.add_argument("--cow", type=Path, default=Path("../cow/corrections/senses.tsv"))
    ap.add_argument("--bahasa", type=Path,
                    default=Path("../Bahasa-Wordnet/corrections/senses.tsv"))
    ap.add_argument("--date", default="2026-10-24")
    ap.add_argument("--release", type=Path, default=Path("../Bahasa-Wordnet/release"))
    ap.add_argument("--cow-release", type=Path, default=Path("../cow/release/cow-1.0.xml"))
    a = ap.parse_args()
    if a.step == "build":
        build(a.triage, a.out, a.size, a.seed)
    elif a.step == "compare":
        compare(a.triage, a.out, 100, a.seed)
    elif a.step == "final":
        final(a.triage, a.out)
    else:
        rel = {"cmn": a.cow_release, "id": a.release / "wnb-id-1.3.xml",
               "zsm": a.release / "wnb-zsm-1.3.xml"}
        corrections(a.out, {"cmn": a.cow, "id": a.bahasa, "zsm": a.bahasa}, rel, a.date)


if __name__ == "__main__":
    main()
