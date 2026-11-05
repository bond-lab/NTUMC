"""Calibrate the sense-review prompt on the items native checkers labelled.

The wnja spot check (docs/quality-sample/spot-check/) gives 290 senses
with a native checker's OK / WRONG / UNSURE.  Each condition below is a
prompt, plus or minus extra context, run blind by a model over the same
items under fresh ids and a fresh shuffle; `score` compares the verdicts
with the checkers.

  strict   the question the issue #8 and JSemCor reviews asked: is the word
           a correct translation of the synset (WRONG if its meaning differs)
  human    the checkers' own instructions: a normal way to express the
           meaning; it may have other meanings
  info     human, plus readings, JMdict glosses (with tags such as archaic),
           the word's other wnja senses and the synset's hypernyms and example
  guided   info, plus guidance drawn from where the reviews went wrong:
           near-synonyms and normal translations are OK; rare or old words
           are OK if a dictionary gives the meaning

  make   write OUT/<condition>/batchNN.tsv, key.tsv and PROMPT.md (with --run N,
         a repeat with fresh ids and shuffle in OUT/<condition>-rN/)
  score  compare OUT/*/batchNN-review.tsv with the checkers

  uv run --with jamdict --with jamdict-data python scripts/prompt_calibration.py make
"""

import argparse
import glob
import random
from collections import Counter, defaultdict
from pathlib import Path

import spot_check as sc
import triage_review as tr

SEED = 20261106
BASE = ["word", "other_words_in_synset", "english_words", "english_definition",
        "own_definition"]
INFO = ["readings", "jmdict", "other_senses_of_word", "english_hypernyms", "english_example"]
COLS = {"strict": BASE, "human": BASE, "info": BASE + INFO, "guided": BASE + INFO}
OUTPUT = ("Write a TSV with the header `id\tverdict\treason` (verdict OK, WRONG or "
          "UNSURE; reason in a few English words) and one row for every input row.")
PROMPTS = {
    "strict": """You are reviewing senses in the Japanese WordNet.  Each row pairs a
Japanese word with one synset, given by its English words and definition and a
Japanese definition.  Decide whether the Japanese word is a correct translation
of this synset.  Answer WRONG if the word means something different (a different
sense of an ambiguous English word, a broader or narrower concept, a related
but different thing), OK if it correctly expresses this synset, and UNSURE if
you cannot tell.""",
    "human": """You are checking senses in the Japanese WordNet, as a native speaker
would.  Each row is a Japanese word with one meaning, given by the English
words and definition (and a definition in Japanese).  For each row decide
whether the word has this meaning in Japanese:
  OK: yes, this is a normal way to express this meaning (it may also have
      other meanings);
  WRONG: no;
  UNSURE: you cannot tell, or it is borderline.
`other_words_in_synset` lists other words given for the same meaning, which may
help; they are not being checked.  Judge each item on its own.""",
}
PROMPTS["info"] = PROMPTS["human"] + """
Extra columns may help: `readings` (kana), `jmdict` (the word's English glosses
in the JMdict dictionary, with tags such as archaic or rare in brackets, senses
separated by |; empty if the word is not in JMdict), `other_senses_of_word`
(English words of the word's other synsets in the Japanese WordNet),
`english_hypernyms` and `english_example` (for the synset).  The Japanese
definition was machine translated and may be wrong; judge the meaning given by
the English."""
PROMPTS["guided"] = PROMPTS["info"] + """
Guidance:
* Judge whether the word can express the meaning, not whether it is the best
  or the only word: a near-synonym or a word translators would normally use
  for it is OK, even if its range is a little wider or narrower.
* A rare, old, literary or technical word is OK if a dictionary gives this
  meaning; do not mark a word WRONG only because it is unfamiliar.
* Mark WRONG when the word does not have this meaning: typically it was
  reached through another sense of an ambiguous English word (a slot in a
  river is not a 銀行), names a related but different thing (an
  institution for an act, a person for a place), or is a different part of
  speech or a fixed phrase that cannot stand for the meaning.
* Use UNSURE sparingly, only when the evidence really is balanced."""


def context(wnja: Path) -> dict[str, dict]:
    """{bare synset or (bare synset, word): extra context} from wnja, omw-en and JMdict."""
    import wn
    from jamdict import Jamdict
    from wn import lmf

    lex = lmf.load(str(wnja / "build" / "wnja-2.1.xml"), progress_handler=None)["lexicons"][0]
    readings, senses = defaultdict(set), defaultdict(set)
    for e in lex["entries"]:
        w = e["lemma"]["writtenForm"]
        readings[w] |= {f["writtenForm"] for f in e.get("forms", []) if f.get("script") == "hira"}
        senses[w] |= {sc.bare(s["synset"]) for s in e["senses"]}
    en, jam = wn.Wordnet("omw-en:2.0"), Jamdict()

    def ensyn(b: str):
        for pos in ([b[-1], "s"] if b.endswith("-a") else [b[-1]]):
            try:
                return en.synset(f"omw-en-{b[:-1]}{pos}")
            except wn.Error:
                continue
        return None

    def jmdict(w: str) -> str:
        out = []
        for ent in jam.lookup(w, strict_lookup=True).entries[:3]:
            for s in ent.senses:
                tags = [m for m in s.misc if m != "word usually written using kana alone"]
                out.append(", ".join(g.text for g in s.gloss)
                           + (f" [{'; '.join(tags)}]" if tags else ""))
        return " | ".join(out[:8])

    return {"readings": readings, "senses": senses, "ensyn": ensyn, "jmdict": jmdict}


def extra(ctx: dict, synset: str, word: str) -> list[str]:
    """The INFO columns for one item."""
    ss = ctx["ensyn"](synset)
    others = []
    for b in sorted(ctx["senses"].get(word, set()) - {synset})[:6]:
        o = ctx["ensyn"](b)
        if o:
            others.append(", ".join(o.lemmas()[:3]))
    hyper = ", ".join(h.lemmas()[0] for h in (ss.hypernyms() if ss else [])[:3])
    ex = (ss.examples() or [""])[0] if ss else ""
    return [" ".join(sorted(ctx["readings"].get(word, set()))), ctx["jmdict"](word),
            " | ".join(others), hyper, ex]


def make(a: argparse.Namespace) -> None:
    """Write one blind batch set per condition."""
    sheet = {r["item"]: r for r in tr.read_tsv(a.spot / "ja-sheet.tsv")}
    key = {k["item"]: k for k in tr.read_tsv(a.spot / "key" / "ja-key.tsv")}
    a.out.mkdir(parents=True, exist_ok=True)
    ctx = context(a.wnja)
    info = {i: extra(ctx, sc.bare(key[i]["synset"]), sheet[i]["word"]) for i in sheet}
    tr.write_tsv(a.out / "info.tsv", ["item", *INFO], [[i, *v] for i, v in info.items()])
    for n, cond in enumerate(COLS):
        if a.conditions and cond not in a.conditions:
            continue
        d = a.out / (cond if a.run == 1 else f"{cond}-r{a.run}")
        d.mkdir(parents=True, exist_ok=True)
        rng = random.Random(SEED + n + 10 * (a.run - 1))
        items = sorted(sheet)
        rng.shuffle(items)
        ids = rng.sample(range(10000, 99999), len(items))
        tr.write_tsv(d / "key.tsv", ["id", "item"], list(zip(ids, items)))
        rows = [[i, *(sheet[it][c] for c in BASE), *(info[it] if cond in ("info", "guided")
                                                      else [])] for i, it in zip(ids, items)]
        for b in range(0, len(rows), a.size):
            tr.write_tsv(d / f"batch{b // a.size + 1:02d}.tsv", ["id", *COLS[cond]],
                         rows[b:b + a.size])
        (d / "PROMPT.md").write_text(PROMPTS[cond] + "\n\n" + OUTPUT + "\n", encoding="utf-8")
    print(len(sheet), "items,", -(-len(sheet) // a.size), "batches per condition")


def verdicts(d: Path) -> dict[str, str]:
    """item -> verdict for one condition."""
    key = {r["id"]: r["item"] for r in tr.read_tsv(d / "key.tsv")}
    out = {}
    for f in sorted(glob.glob(f"{d}/batch[0-9][0-9]-review.tsv")):
        for r in tr.read_tsv(Path(f)):
            if r.get("id") in key:
                out[key[r["id"]]] = (r.get("verdict") or "").strip().upper()
    return out


def score(a: argparse.Namespace) -> None:
    """Agreement of each condition with the first checker (after the second look)."""
    key = {k["item"]: k for k in tr.read_tsv(a.spot / "key" / "ja-key.tsv")}
    one = {i: r["meaning"].strip().upper() for i, r in sc.answers(a.spot, "ja").items()}
    two = {r["item"]: r["meaning"].strip().upper()
           for r in tr.read_tsv(sc.filled(a.spot, "ja-overlap-sheet.tsv"))}
    rows = []
    for d in sorted(p for p in a.out.iterdir() if (p / "key.tsv").exists()):
        cond = d.name
        v = verdicts(d)
        if not v:
            continue
        pairs = [(one[i], v[i]) for i in v if one.get(i) in ("OK", "WRONG")]
        definite = [(h, m) for h, m in pairs if m in ("OK", "WRONG")]
        agree = sum(h == m for h, m in definite)
        c = Counter(definite)
        prec = c[("WRONG", "WRONG")] / max(1, c[("WRONG", "WRONG")] + c[("OK", "WRONG")])
        rec = c[("WRONG", "WRONG")] / max(1, c[("WRONG", "WRONG")] + c[("WRONG", "OK")])
        k1 = sc.kappa(definite)
        k2 = sc.kappa([(two[i], v[i]) for i in two if two[i] in ("OK", "WRONG")
                       and v.get(i) in ("OK", "WRONG")])
        unsure = sum(m == "UNSURE" for _, m in pairs)
        rows.append([cond, len(v), len(definite), f"{agree / len(definite):.3f}", f"{k1:.2f}",
                     f"{k2:.2f}" if k2 is not None else "", f"{prec:.2f}", f"{rec:.2f}", unsure,
                     c[("OK", "WRONG")]])
        strata = defaultdict(Counter)
        for i, m in v.items():
            if one.get(i) in ("OK", "WRONG") and m in ("OK", "WRONG"):
                strata[key[i]["stratum"]]["agree" if one[i] == m else "disagree"] += 1
        print(cond, {s: f"{x['agree']}/{x['agree'] + x['disagree']}"
                     for s, x in sorted(strata.items())})
    head = ["condition", "answered", "definite", "agreement", "kappa1", "kappa2",
            "wrong_precision", "wrong_recall", "unsure", "good_called_wrong"]
    tr.write_tsv(a.out / "score.tsv", head, rows)
    print("\t".join(head))
    for r in rows:
        print("\t".join(map(str, r)))


def main() -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("make", "score"))
    ap.add_argument("--wnja", type=Path, default=Path("../wnja"), help="wnja checkout, built")
    ap.add_argument("--spot", type=Path, default=Path("docs/quality-sample/spot-check"))
    ap.add_argument("--out", type=Path, default=Path("build/calibration"))
    ap.add_argument("--size", type=int, default=100)
    ap.add_argument("--run", type=int, default=1,
                    help="repeat run: fresh ids and shuffle, in <condition>-rN/")
    ap.add_argument("--conditions", nargs="*", help="make only these conditions")
    a = ap.parse_args()
    make(a) if a.step == "make" else score(a)


if __name__ == "__main__":
    main()
