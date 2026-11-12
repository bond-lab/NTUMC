"""How far wnja and the NTU-MC Japanese wordnet have diverged (read only).

For deciding which should be the master copy of the Japanese wordnet.
Compares wnja (its corrections and its built XML) with the NTU-MC wordnet
database and the Japanese corpus, and writes to OUT:

  corrections.tsv   each wnja sense correction (last row per sense), whether
                    the sense is in NTU-MC, and how many corpus concepts are
                    tagged with it (same lemma) or with its synset (any lemma)
  definitions.tsv   each wnja definition fix, and whether NTU-MC still has
                    the old text
  uncovered.tsv     corpus (synset, lemma) tags that no wnja sense covers
                    (no entry for the synset with that lemma or form, after
                    dropping the '_' and spaces of multiword lemmas), and
                    whether NTU-MC has the sense
  summary.tsv       the counts, including how many corpus concepts each
                    wordnet covers and the NTU-MC senses wnja lacks under
                    any spelling

  wnja_ntumc_report.py [--wnja ../wnja] [--wn build/wn-ntumc.db]
                       [--corpus build/jpn.db] [--out build/wnja-ntumc-report]
"""

import argparse
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import triage_review as tr

# concept tags that are not synsets (e for error, x for not a concept, ...)
SYNSET_TAG = "%-_"


def norm(lemma: str) -> str:
    """A corpus lemma without the '_' and spaces that join multiword expressions."""
    return lemma.replace("_", "").replace(" ", "")


def bare(synset: str) -> str:
    """'wnja-00001740-n' -> '00001740-n'."""
    return synset.removeprefix("wnja-")


def last_rows(path: Path) -> dict[tuple[str, str], dict]:
    """(bare synset, lemma) -> the last correction row for it (as the build applies them)."""
    return {(bare(r["synset_id"]), r["lemma"]): r for r in tr.read_tsv(path)}


def ntumc_senses(db: Path) -> set[tuple[str, str]]:
    """(synset, lemma) of every Japanese sense in the NTU-MC wordnet."""
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
        return set(con.execute(
            "SELECT s.synset, w.lemma FROM sense s JOIN word w ON s.wordid = w.wordid "
            "WHERE s.lang = 'jpn'"))


def spellings_of(lemma: str) -> set[str]:
    """An NTU-MC lemma as wnja may spell it: without '+' joins, and a する
    verb (区分+する) also as its noun (区分)."""
    out = {lemma, lemma.replace("+", ""), norm(lemma.replace("+", ""))}
    if lemma.endswith("+する"):
        out.add(lemma.removesuffix("+する"))
    return out


def ntumc_spellings(senses: set[tuple[str, str]]) -> dict[str, set[str]]:
    """synset -> the spellings of its NTU-MC Japanese senses (see spellings_of)."""
    out = defaultdict(set)
    for synset, lemma in senses:
        out[synset] |= spellings_of(lemma)
    return out


def ntumc_defs(db: Path) -> dict[str, set[str]]:
    """synset -> its Japanese definitions in NTU-MC, each part and all parts
    joined with '; ' (as wnja joins them)."""
    parts = defaultdict(list)
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
        for synset, d in con.execute(
                "SELECT synset, def FROM synset_def WHERE lang = 'jpn' ORDER BY synset, sid"):
            parts[synset].append(d)
    return {s: set(ds) | {"; ".join(ds)} for s, ds in parts.items()}


def corpus_tags(db: Path) -> Counter:
    """(synset, clemma) -> number of corpus concepts tagged with it."""
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
        return Counter(con.execute(
            "SELECT tag, clemma FROM concept WHERE tag LIKE ?", (SYNSET_TAG,)))


def wnja_spellings(xml: Path) -> tuple[dict[str, set[str]], set[tuple[str, str]]]:
    """synset -> lemmas and forms of its wnja senses; and the (synset, lemma) senses."""
    from wn import lmf

    lex = lmf.load(str(xml), progress_handler=None)["lexicons"][0]
    spell, senses = defaultdict(set), set()
    for e in lex["entries"]:
        lemma = e["lemma"]["writtenForm"]
        forms = {lemma} | {f["writtenForm"] for f in e.get("forms", [])}
        for s in e["senses"]:
            spell[bare(s["synset"])] |= forms
            senses.add((bare(s["synset"]), lemma))
    return spell, senses


def run(a: argparse.Namespace) -> None:
    """Write the report files and print the summary."""
    corr = last_rows(a.wnja / "corrections" / "senses.tsv")
    ntumc = ntumc_senses(a.wn)
    tags = corpus_tags(a.corpus)
    by_synset = Counter()
    for (synset, _), n in tags.items():
        by_synset[synset] += n
    rows, summ = [], Counter()
    for (synset, lemma), r in sorted(corr.items()):
        act = r["action"]
        in_ntumc = (synset, lemma) in ntumc
        same = tags.get((synset, lemma), 0)
        rows.append([synset, lemma, act, r.get("new_lemma", ""), r["source"],
                     "yes" if in_ntumc else "no", same, by_synset.get(synset, 0)])
        summ[(act, "in NTU-MC" if in_ntumc else "not in NTU-MC")] += 1
        if same:
            summ[(act, "senses tagged in corpus")] += 1
            summ[(act, "corpus concepts")] += same
    tr.write_tsv(a.out / "corrections.tsv",
                 ["synset", "lemma", "action", "new_lemma", "source", "in_ntumc",
                  "corpus_same_lemma", "corpus_synset"], rows)

    defs = ntumc_defs(a.wn)
    drows = []
    for r in tr.read_tsv(a.wnja / "corrections" / "definitions.tsv"):
        s = bare(r["synset_id"])
        state = ("old text" if r["old_value"] in defs.get(s, set()) else
                 "already fixed" if r["new_value"] in defs.get(s, set()) else "differs")
        drows.append([s, state, r["old_value"], r["new_value"], r["source"]])
        summ[("definitions", f"NTU-MC has {state}")] += 1
    tr.write_tsv(a.out / "definitions.tsv",
                 ["synset", "ntumc", "old_value", "new_value", "source"], drows)

    spell, wsenses = wnja_spellings(a.wnja / "build" / "wnja-2.1.xml")
    ntspell = ntumc_spellings(ntumc)
    urows = []
    for (synset, clemma), n in tags.most_common():
        summ[("corpus", "concepts")] += n
        in_w = norm(clemma) in spell.get(synset, set())
        in_nt = norm(clemma) in ntspell.get(synset, set())
        summ[("corpus covered", {(True, True): "by both", (True, False): "by wnja only",
                                 (False, True): "by NTU-MC only",
                                 (False, False): "by neither"}[(in_w, in_nt)])] += n
        if in_w:
            continue
        removed = corr.get((synset, clemma), {}).get("action", "")
        why = ("removed in wnja" if removed == "remove" else
               "renamed in wnja" if removed == "rename" else
               "synset has no wnja sense" if synset not in spell else
               "lemma not in wnja for this synset")
        urows.append([synset, clemma, n, why, "yes" if in_nt else "no"])
    tr.write_tsv(a.out / "uncovered.tsv",
                 ["synset", "clemma", "concepts", "why", "ntumc_sense"], urows)

    nt_only = [(sy, le) for sy, le in ntumc if not spellings_of(le) & spell.get(sy, set())]
    summ[("senses", "NTU-MC jpn")] = len(ntumc)
    summ[("senses", "wnja")] = len(wsenses)
    summ[("senses", "NTU-MC only (any spelling)")] = len(nt_only)
    for sy, le in nt_only:
        act = corr.get((sy, le), {}).get("action", "")
        summ[("NTU-MC only", f"{act} in wnja" if act else "dropped by the wnja build")] += 1
    out = [[k[0], k[1], v] for k, v in sorted(summ.items())]
    tr.write_tsv(a.out / "summary.tsv", ["what", "detail", "count"], out)
    for r in out:
        print("\t".join(map(str, r)))


def main() -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wnja", type=Path, default=Path("../wnja"), help="wnja checkout, built")
    ap.add_argument("--wn", type=Path, default=Path("build/wn-ntumc.db"))
    ap.add_argument("--corpus", type=Path, default=Path("build/jpn.db"))
    ap.add_argument("--out", type=Path, default=Path("build/wnja-ntumc-report"))
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    run(a)


if __name__ == "__main__":
    main()
