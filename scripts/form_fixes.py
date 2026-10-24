"""Mechanical lemma form fixes for COW, wnja and Wordnet Bahasa, as rename rows.

Finds lemmas whose written form is damaged in a way that needs no review
and adds ``rename`` rows (with ``new_lemma``) to the release repository's
corrections/senses.tsv; existing ``add`` and ``rename`` rows get the fixed
form in place.  The fixes are

  all     strip leading and trailing space, collapse runs of spaces
  cmn     full-width digits and Latin letters to half width; join Han
          characters separated by spaces; traditional characters to
          simplified (OpenCC t2s), only when every simplified character is
          in the basic CJK block (so 鰤 is kept rather than becoming 𫚕)
  ja      full-width digits and Latin letters to half width; katakana typed
          for hiragana okurigana (TYPOS, checked by hand)

  form_fixes.py LANG BASE_XML CORRECTIONS_TSV [--prefix OLD NEW]

BASE_XML is the input of the release build (the NTU-MC export for COW and
Bahasa, wnja-2.0.xml for wnja); --prefix maps its synset ids to those of
the corrections file (e.g. ntumc-cmn cow).
"""

import argparse
import re
import unicodedata
from pathlib import Path

import triage_review as tr

FULL_WIDTH = re.compile("[０-９Ａ-Ｚａ-ｚ]+")
HAN = r"[一-鿿㐀-䶿]"
HAN_SPACE = re.compile(rf"(?<={HAN}) +(?={HAN})")
TYPOS = {"跡取リ": "跡取り", "走リ": "走り"}  # 中央ハ (middle C) is right
SOURCE = "form: mechanical"


def rare_han(s: str) -> set[str]:
    """Han characters of s outside the basic CJK block."""
    return {c for c in s if "\u3400" <= c <= "\u4dbf" or ord(c) > 0xFFFF}


def fix_steps(lang: str, form: str, t2s=None) -> tuple[str, list[str]]:
    """The fixed written form and the names of the fixes that changed it."""
    steps = []

    def step(name: str, new: str) -> str:
        if new != cur:
            steps.append(name)
        return new

    cur = form
    cur = step("stray space", " ".join(cur.split()))
    if lang in ("cmn", "ja"):
        cur = step("full-width characters",
                   FULL_WIDTH.sub(lambda m: unicodedata.normalize("NFKC", m.group()), cur))
    if lang == "cmn":
        cur = step("spaces between Han characters", HAN_SPACE.sub("", cur))
        simp = t2s.convert(cur) if t2s else cur
        if rare_han(simp) <= rare_han(cur):
            cur = step("traditional characters", simp)
    if lang == "ja":
        cur = step("katakana for hiragana okurigana", TYPOS.get(cur, cur))
    return cur, steps


def fix_form(lang: str, form: str, t2s=None) -> str:
    """The fixed written form (the form itself if nothing needs fixing)."""
    return fix_steps(lang, form, t2s)[0]


def base_senses(xml: Path, old: str, new: str) -> list[tuple[str, str]]:
    """(synset id with the corrections prefix, lemma) of every sense in xml."""
    from wn import lmf

    lex = lmf.load(str(xml), progress_handler=None)["lexicons"][0]
    return [(s["synset"].replace(old, new, 1), e["lemma"]["writtenForm"])
            for e in lex["entries"] for s in e.get("senses", [])]


def update(lang: str, senses: list[tuple[str, str]], rows: list[dict], date: str,
           t2s=None) -> tuple[list[dict], dict]:
    """Corrections rows with the form fixes applied; and counts of what changed."""
    fix = lambda f: fix_form(lang, f, t2s)
    out, n = [], {"rename added": 0, "add fixed": 0, "rename fixed": 0, "skipped": 0}
    have = {(r["synset_id"], r["lemma"]): r for r in rows}
    for r in rows:
        r = dict(r)
        if r["action"] == "add":
            if fix(r["lemma"]) != r["lemma"]:
                r["lemma"] = fix(r["lemma"])
                n["add fixed"] += 1
        elif r["action"] == "rename" and fix(r.get("new_lemma", "")) != r.get("new_lemma", ""):
            r["new_lemma"] = fix(r["new_lemma"])
            n["rename fixed"] += 1
        out.append(r)
    for ss, lemma in sorted(set(senses)):
        new = fix(lemma)
        if new == lemma:
            continue
        if (ss, lemma) in have:  # already removed, renamed or lowered
            n["skipped"] += have[(ss, lemma)]["action"] == "lower"
            continue
        out.append({"synset_id": ss, "lemma": lemma, "action": "rename", "confidence": "",
                    "reason": ", ".join(fix_steps(lang, lemma, t2s)[1]), "source": SOURCE, "date": date,
                    "new_lemma": new})
        n["rename added"] += 1
    return out, n


def main() -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lang", choices=("cmn", "ja", "id", "zsm"))
    ap.add_argument("xml", type=Path)
    ap.add_argument("corrections", type=Path)
    ap.add_argument("--prefix", nargs=2, default=("", ""), metavar=("OLD", "NEW"))
    ap.add_argument("--date", default="2026-10-24")
    a = ap.parse_args()
    t2s = None
    if a.lang == "cmn":
        from opencc import OpenCC
        t2s = OpenCC("t2s")
    mine = a.prefix[1] + "-"  # rows of earlier runs for this lexicon are replaced
    rows = [r for r in tr.read_tsv(a.corrections)
            if r["source"] != SOURCE or not r["synset_id"].startswith(mine)]
    head = list(rows[0]) if rows else tr.CORR_HEAD
    if "new_lemma" not in head:
        head.append("new_lemma")
    out, n = update(a.lang, base_senses(a.xml, *a.prefix), rows, a.date, t2s)
    k = len(rows)  # keep the order of the old rows, new rows sorted at the end
    tr.write_tsv(a.corrections, head, [[r.get(c, "") for c in head] for r in out[:k]]
                 + sorted([r.get(c, "") for c in head] for r in out[k:]))
    print(a.lang, n)


if __name__ == "__main__":
    main()
