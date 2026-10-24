"""Human spot check of the LLM review decisions for COW and Wordnet Bahasa.

  make   draw a stratified sample of the released decisions and write, per
         language, a blind sheet for a native-speaker checker (no model
         verdicts) and a key with the decision and stratum of each item
  score  compare filled-in sheets with the keys: agreement per stratum
         with a 95% Wilson interval, and estimates weighted by stratum size

  spot_check.py make  [--out docs/quality-sample/spot-check] [--n 20]
  spot_check.py score [--out docs/quality-sample/spot-check]

The strata come from what the release does to a sense (the corrections
files) and from the review (final.tsv):

  remove-wrong        removed, both Opus runs judged it wrong
  remove-wrong-adj    removed, wrong by adjudication
  remove-form         removed for a form note (malformed, other variety)
  keep                flagged by triage, judged right by both runs
  keep-adj            flagged, judged right by adjudication
  lower               undecided, confidence lowered to 0.5
  unflagged           not flagged by triage (estimates what triage missed)
  rename              malformed lemma given a fixed form (cmn)
  rename-mechanical   form_fixes.py renames (cmn)
  rescue              added from excluded sources (cmn)
  move                added from the other variety of Malay (zsm, id)
"""

import argparse
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

import triage_review as tr

SEED = 20261024
LANGS = {"cmn": "../cow/corrections/senses.tsv",
         "id": "../Bahasa-Wordnet/corrections/senses.tsv",
         "zsm": "../Bahasa-Wordnet/corrections/senses.tsv"}
PREFIX = {"cmn": "cow-", "id": "wnb-id-", "zsm": "wnb-zsm-"}
OTHER = {"id": "zsm", "zsm": "id"}
VARIETY = {"cmn": "", "id": "Malaysian only", "zsm": "Indonesian only"}
BIG = {"unflagged": 2}  # multiples of --n for strata with few expected errors
SHEET = ["item", "word", "other_words_in_synset", "english_words", "english_definition",
         "own_definition", "meaning", "form", "comment"]
KEY = ["item", "stratum", "synset", "word", "old_word", "decision", "decided_by",
       "model_reason"]
# what the decision means for the checker's answer
EXPECT = {"remove-wrong": "WRONG", "remove-wrong-adj": "WRONG", "remove-form": "BAD",
          "keep": "OK", "keep-adj": "OK", "unflagged": "OK", "rename": "OK",
          "rename-mechanical": "OK", "rescue": "OK", "move": "OK", "lower": None}


def stratum(r: dict) -> str:
    """Stratum of a corrections row."""
    src, act = r["source"], r["action"]
    if act == "rename":
        return "rename-mechanical" if src.startswith("form:") else "rename"
    if act == "add":
        return "rescue" if src.startswith("rescue") else "move"
    if act == "lower":
        return "lower"
    if "form note" in src:
        return "remove-form"
    return "remove-wrong-adj" if "adjudicated" in src else "remove-wrong"


def rows_by_sense(d: Path) -> dict:
    """{(synset, word): row} of the batch files in d."""
    return {(r["synset"], r["word"]): r
            for f in sorted(d.glob("batch[0-9][0-9][0-9].tsv")) for r in tr.read_tsv(f)}


def population(lang: str, a: argparse.Namespace) -> dict[str, list[dict]]:
    """Candidate items per stratum, each with its triage (or rescue) context."""
    triaged = rows_by_sense(a.triage / lang)
    flagged = {(r["synset"], r["word"]) for r in tr.flagged(a.triage, lang)}
    ctx = {**(rows_by_sense(a.rescue / lang) if lang == "cmn" else {}), **triaged}
    other_ctx = rows_by_sense(a.triage / OTHER[lang]) if lang in OTHER else {}
    corr = [r for r in tr.read_tsv(Path(LANGS[lang])) if r["synset_id"].startswith(PREFIX[lang])]
    done = {(r["synset_id"], r["lemma"]) for r in corr}
    final = {(r["synset"], r["word"]): r for r in tr.read_tsv(a.review / lang / "final.tsv")}
    if lang == "cmn":
        final.update({(r["synset"], r["word"]): r
                      for r in tr.read_tsv(a.rescue_review / "cmn" / "final.tsv")})
    pop = defaultdict(list)
    for r in corr:
        key = (r["synset_id"], r["lemma"])
        s = stratum(r)
        c = ctx.get(key) or ctx.get((r["synset_id"], r["lemma"].replace("+", "")))
        if s == "move":  # context from the variety it was moved from
            src = PREFIX[OTHER[lang]] + r["synset_id"].removeprefix(PREFIX[lang])
            c, f = other_ctx.get((src, r["lemma"])), final_of(a, OTHER[lang], src, r["lemma"])
        else:
            f = final.get(key) or final.get((r["synset_id"], r["lemma"].replace("+", "")))
        if c is None:
            continue
        pop[s].append({"ctx": c, "synset": r["synset_id"], "word": r.get("new_lemma") or r["lemma"].replace("+", ""),
                       "old_word": r["lemma"] if r.get("new_lemma") else "",
                       "decision": r["action"], "decided_by": (f or {}).get("decided_by", ""),
                       "model_reason": r["reason"]})
    for key, f in final.items():
        if key in done or f["action"] != "keep" or key not in ctx:
            continue
        if f["haiku_reason"].startswith("candidate"):  # rescue candidates not added
            continue
        s = "keep-adj" if f["decided_by"] == "adjudication" else "keep"
        pop[s].append({"ctx": ctx[key], "synset": key[0], "word": key[1], "old_word": "", "decision": "keep",
                       "decided_by": f["decided_by"], "model_reason": f["reason"]})
    for key, c in triaged.items():
        if key not in flagged and key not in done:
            pop["unflagged"].append({"ctx": c, "synset": key[0], "word": key[1], "old_word": "",
                                     "decision": "keep", "decided_by": "triage",
                                     "model_reason": ""})
    return pop


_final_cache: dict[str, dict] = {}


def final_of(a: argparse.Namespace, lang: str, synset: str, word: str) -> dict | None:
    """The final.tsv row of another language for (synset, word)."""
    if lang not in _final_cache:
        _final_cache[lang] = {(r["synset"], r["word"]): r
                              for r in tr.read_tsv(a.review / lang / "final.tsv")}
    return _final_cache[lang].get((synset, word))


def make(a: argparse.Namespace) -> None:
    """Write <lang>-sheet.tsv, key/<lang>-key.tsv and key/strata.tsv."""
    (a.out / "key").mkdir(parents=True, exist_ok=True)
    strata_rows = []
    for lang in LANGS:
        pop = population(lang, a)
        rng = random.Random(f"{SEED}-{lang}")
        items = []
        for s in sorted(pop):
            k = min(len(pop[s]), a.n * BIG.get(s, 1))
            items += [(s, x) for x in rng.sample(sorted(pop[s], key=lambda x: (
                x["synset"], x["word"])), k)]
            strata_rows.append([lang, s, len(pop[s]), k])
        rng.shuffle(items)
        sheet, key = [], []
        for i, (s, x) in enumerate(items, 1):
            c, item = x["ctx"], f"{lang}-{i:03d}"
            others = " ".join(w for w in c["other_words_in_synset"].split() if w != x["word"])
            sheet.append([item, x["word"], others, c["english_words"], c["english_definition"],
                          c["own_definition"], "", "", ""])
            key.append([item, s, x["synset"], x["word"], x["old_word"], x["decision"],
                        x["decided_by"], x["model_reason"]])
        tr.write_tsv(a.out / f"{lang}-sheet.tsv", SHEET, sheet)
        tr.write_tsv(a.out / "key" / f"{lang}-key.tsv", KEY, key)
        print(lang, len(sheet), "items")
    tr.write_tsv(a.out / "key" / "strata.tsv", ["lang", "stratum", "population", "sample"],
                 strata_rows)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for k successes out of n."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, mid - half), min(1.0, mid + half)


def agrees(stratum_name: str, meaning: str, form: str) -> bool | None:
    """Whether the checker's answer supports the decision (None: no answer or lower)."""
    meaning, form = meaning.strip().upper(), form.strip().upper()
    want = EXPECT[stratum_name]
    if not meaning or want is None:
        return None
    if want == "BAD":
        return form not in ("", "OK")
    if want == "WRONG":
        return meaning == "WRONG"
    return meaning == "OK" and form in ("", "OK")


def score(a: argparse.Namespace) -> None:
    """Print agreement per stratum and stratum-weighted estimates per language."""
    pops = {(r["lang"], r["stratum"]): int(r["population"])
            for r in tr.read_tsv(a.out / "key" / "strata.tsv")}
    out = []
    for lang in LANGS:
        sheet = a.out / f"{lang}-sheet.tsv"
        if not sheet.exists():
            continue
        ans = {r["item"]: r for r in tr.read_tsv(sheet)}
        res = defaultdict(Counter)
        for k in tr.read_tsv(a.out / "key" / f"{lang}-key.tsv"):
            r = ans.get(k["item"], {})
            ok = agrees(k["stratum"], r.get("meaning", ""), r.get("form", ""))
            if k["stratum"] == "lower" and r.get("meaning", "").strip():
                res["lower"][r["meaning"].strip().upper()] += 1
            elif ok is not None:
                res[k["stratum"]]["agree" if ok else "disagree"] += 1
        for s, c in sorted(res.items()):
            n = c["agree"] + c["disagree"]
            if s == "lower":
                out.append([lang, s, pops.get((lang, s), ""), sum(c.values()),
                            " ".join(f"{v}:{c[v]}" for v in sorted(c)), "", ""])
                continue
            lo, hi = wilson(c["agree"], n)
            out.append([lang, s, pops.get((lang, s), ""), n, f"{c['agree'] / n:.2f}" if n else "",
                        f"{lo:.2f}", f"{hi:.2f}"])
    tr.write_tsv(a.out / "key" / "score.tsv",
                 ["lang", "stratum", "population", "checked", "agreement", "low95", "high95"], out)
    for row in out:
        print("\t".join(map(str, row)))


def main() -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("make", "score"))
    ap.add_argument("--out", type=Path, default=Path("docs/quality-sample/spot-check"))
    ap.add_argument("--n", type=int, default=20, help="items per stratum")
    ap.add_argument("--triage", type=Path, default=Path("build/triage"))
    ap.add_argument("--review", type=Path, default=Path("build/triage-opus"))
    ap.add_argument("--rescue", type=Path, default=Path("build/rescue"))
    ap.add_argument("--rescue-review", type=Path, default=Path("build/rescue-opus"))
    a = ap.parse_args()
    make(a) if a.step == "make" else score(a)


if __name__ == "__main__":
    main()
