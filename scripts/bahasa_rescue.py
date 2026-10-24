"""Find Indonesian words for Wordnet Bahasa synsets that only have a definition.

wnb-id has synsets with an Indonesian definition (from wn-ind-def.tab) but
no Indonesian word.  Candidate words come from two places:

  * wn-msa-all.tab senses for the synset that the release leaves out
    (automatic O not in the NTU-MC database, M and L; never X, and never
    one the 1.4 review removed);
  * words proposed by a model, for synsets with no O or M candidate.

This script

  generate    writes the synsets that need proposals, in batches, to
              OUT/generate/batchNNN.tsv (a model writes batchNNN-words.tsv)
  candidates  writes all candidates in the triage format (all flagged) to
              OUT/id/batch001.tsv, so that triage_review.py build/compare/final
              can review them blind, and OUT/sources.tsv
  adds        appends the candidates judged OK (with no FORM or MS note from
              both runs) to Wordnet Bahasa's corrections/senses.tsv as add rows

  bahasa_rescue.py generate WNB_ID_XML --en-data WN_DIR
  bahasa_rescue.py candidates WNB_ID_XML --en-data WN_DIR
  bahasa_rescue.py adds
"""

import argparse
import glob
from pathlib import Path

import triage_review as tr

HEAD = ["id", "synset", "word", "other_words_in_synset", "english_words",
        "english_definition", "own_definition"]
GEN_HEAD = ["id", "synset", "english_words", "english_definition", "own_definition"]
TAB_STATUS = ("O", "M", "L")


def wordless(xml: Path, en_data: Path) -> dict[str, tuple[str, str, str]]:
    """{synset id: (english words, english definition, own definition)} for
    the synsets of xml that have a definition but no members."""
    import wn
    from wn import lmf

    wn.config.data_directory = str(en_data)
    en = wn.Wordnet("omw-en:2.0")
    lex = lmf.load(str(xml), progress_handler=None)["lexicons"][0]
    out = {}
    for ss in lex["synsets"]:
        if ss.get("members") or not ss.get("definitions"):
            continue
        ew = ed = ""
        if ss.get("ili") and ss["ili"] != "in" and (e := en.synsets(ili=ss["ili"])):
            ew, ed = ", ".join(e[0].lemmas()), e[0].definition() or ""
        out[ss["id"]] = (ew, ed, ss["definitions"][0]["text"])
    return out


def tab_candidates(tab: Path, synsets: set[str], corr: Path) -> dict[str, dict[str, str]]:
    """{synset id: {lemma: status}} from wn-msa-all.tab (Indonesian or both),
    leaving out X and senses the corrections already decided."""
    decided = {(r["synset_id"], r["lemma"]) for r in tr.read_tsv(corr)}
    bad, cand = set(), {}
    with open(tab, encoding="utf-8") as fh:
        for line in fh:
            p = line.rstrip("\n").split("\t")
            if len(p) != 4 or p[1] not in ("B", "I"):
                continue
            sid, status, lemma = "wnb-id-" + p[0], p[2], p[3].strip()
            if sid not in synsets or not lemma:
                continue
            if status == "X":
                bad.add((sid, lemma))
            elif status in TAB_STATUS and (sid, lemma) not in decided:
                best = cand.setdefault(sid, {}).get(lemma)
                if best is None or TAB_STATUS.index(status) < TAB_STATUS.index(best):
                    cand[sid][lemma] = status
    for sid, lemma in bad:
        cand.get(sid, {}).pop(lemma, None)
    return {s: c for s, c in cand.items() if c}


def generate(a: argparse.Namespace) -> None:
    """Write batches of synsets with no O or M candidate for word proposals."""
    empty = wordless(a.xml, a.en_data)
    cand = tab_candidates(a.tab, set(empty), a.corrections)
    todo = [s for s in sorted(empty)
            if not any(v in ("O", "M") for v in cand.get(s, {}).values())]
    d = a.out / "generate"
    d.mkdir(parents=True, exist_ok=True)
    for b in range(0, len(todo), a.size):
        tr.write_tsv(d / f"batch{b // a.size + 1:03d}.tsv", GEN_HEAD,
                     [[f"g{n}", s, *empty[s]] for n, s in enumerate(todo[b:b + a.size], b + 1)])
    print(f"{len(empty)} wordless synsets, {len(cand)} with tab candidates, "
          f"{len(todo)} to propose words for -> {-(-len(todo) // a.size)} batches")


def proposals(d: Path) -> dict[str, set[str]]:
    """{synset id: words} from the generate/batchNNN-words.tsv files."""
    synset = {}
    for f in sorted(glob.glob(f"{d}/batch[0-9][0-9][0-9].tsv")):
        synset.update({r["id"]: r["synset"] for r in tr.read_tsv(Path(f))})
    out = {}
    for f in sorted(glob.glob(f"{d}/batch[0-9][0-9][0-9]-words.tsv")):
        for r in tr.read_tsv(Path(f)):
            if r.get("id") in synset:
                for w in (r.get("words") or "").split(";"):
                    if w.strip():
                        out.setdefault(synset[r["id"]], set()).add(w.strip())
    return out


def candidates(a: argparse.Namespace) -> None:
    """Write OUT/id/batch001.tsv (all flagged) and OUT/sources.tsv."""
    empty = wordless(a.xml, a.en_data)
    src: dict[tuple[str, str], str] = {}
    for sid, forms in tab_candidates(a.tab, set(empty), a.corrections).items():
        for lemma, status in forms.items():
            src[(sid, lemma)] = f"tab {status}"
    for sid, words in proposals(a.out / "generate").items():
        for w in words:
            src.setdefault((sid, w), "proposed")
    forms: dict[str, list[str]] = {}
    for sid, w in sorted(src):
        forms.setdefault(sid, []).append(w)
    rows = []
    for sid, ws in forms.items():
        for w in ws:
            others = " ".join(o for o in ws if o != w)
            rows.append([f"id001-{len(rows) + 1}", sid, w, others, *empty[sid]])
    for lang in tr.LANGS:
        (a.out / lang).mkdir(parents=True, exist_ok=True)
    tr.write_tsv(a.out / "id" / "batch001.tsv", HEAD, rows)
    tr.write_tsv(a.out / "id" / "batch001-suspects.tsv", ["id", "word", "reason"],
                 [[r[0], r[2], "candidate"] for r in rows])
    tr.write_tsv(a.out / "sources.tsv", ["synset", "word", "source"],
                 [[s, w, v] for (s, w), v in sorted(src.items())])
    kinds = {}
    for v in src.values():
        kinds[v] = kinds.get(v, 0) + 1
    print(f"{len(forms)} synsets, {len(rows)} candidate senses", kinds)


def adds(a: argparse.Namespace) -> None:
    """Append add rows for candidates judged OK to the Bahasa corrections."""
    final = tr.read_tsv(a.review / "id" / "final.tsv")
    src = {(r["synset"], r["word"]): r["source"] for r in tr.read_tsv(a.out / "sources.tsv")}
    old = tr.read_tsv(a.corrections)
    new = [[r["synset"], r["word"], "add", "",
            f"{src[(r['synset'], r['word'])]}: {r['reason']}".rstrip(": "),
            "lemma rescue: 2 blind opus" + (" (adjudicated)" if r["decided_by"] == "adjudication"
                                            else ""), a.date, ""]
           for r in final if r["final"] == "OK"
           and not {"FORM", "MS"} & set(r["note_both"].split())]
    keep = [[r[c] for c in tr.CORR_HEAD] for r in old
            if not r["source"].startswith("lemma rescue")]
    tr.write_tsv(a.corrections, tr.CORR_HEAD, keep + sorted(new))
    print(f"{len(new)} add rows of {len(final)} candidates in "
          f"{len({r[0] for r in new})} synsets")


def main() -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("generate", "candidates", "adds"))
    ap.add_argument("xml", type=Path, nargs="?", help="wnb-id XML with the corrections applied")
    ap.add_argument("--en-data", type=Path, default=Path.home() / ".wn_data",
                    help="wn data directory with omw-en:2.0")
    ap.add_argument("--tab", type=Path, default=Path("../Bahasa-Wordnet/data/wn-msa-all.tab"))
    ap.add_argument("--corrections", type=Path,
                    default=Path("../Bahasa-Wordnet/corrections/senses.tsv"))
    ap.add_argument("--out", type=Path, default=Path("build/bahasa-rescue"))
    ap.add_argument("--review", type=Path, default=Path("build/bahasa-rescue-opus"))
    ap.add_argument("--size", type=int, default=100)
    ap.add_argument("--date", default="2026-10-24")
    a = ap.parse_args()
    {"generate": generate, "candidates": candidates, "adds": adds}[a.step](a)


if __name__ == "__main__":
    main()
