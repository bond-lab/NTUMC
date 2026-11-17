#!/usr/bin/env python3
"""Make the concordance of the corpus display, and its links to the wordnets.

    .venv/bin/python scripts/make_concordance.py [--outdir display] [--wordnet DIR]

Run after make_display.py.  For every synset the corpus is tagged with,
the sentences that use it are written to OUTDIR/data/conc/, in SHARDS
files, and OUTDIR/concept.html shows them: concept.html?synset=TAG.
Only documents that have a page in OUTDIR are read.

With --wordnet, DIR is the web directory of a Cygnet build of the
wordnets (cygnet.db and provenance.db).  Two more files link the two
ways:

* OUTDIR/data/wn-links.json: for a synset of the corpus, the row id of
  its concept in Cygnet.  The corpus pages link to the concept.
* DIR/corpus-index.json: for a concept of Cygnet, its synset in the
  corpus and how many times it is used.  Cygnet links to concept.html
  (the ``corpus`` key of its local.json).

Cygnet's row ids change with each build, so run this again after one.
"""

import argparse
import csv
import json
import logging
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from make_display import _get_env, compute_nospace

from ntumc.corpus import Sentence, db

SHARDS = 512
CAP = 100  # examples kept for one synset in one language; the count is of them all
SYNSET = re.compile(r"\d{8}-[a-z]")
ILI_MAP = ROOT / "build" / "ili-map-pwn30.tab"
REGISTRY = ROOT.parent / "omw-ntumc" / "data" / "registry.tsv"
# the wordnets whose synset ids are a prefix and the corpus's synset
LEXICONS = ["cow-min", "cow", "wnja-min", "wnja", "wnb-id-min", "wnb-id",
            "wnb-zsm-min", "wnb-zsm", "wncze-min", "wncze"]

# the display's languages whose wordnet is in the Cygnet build, and Cygnet's code for each
WN_LANGS = {"eng": "en", "cmn": "cmn-Hans", "jpn": "ja", "ind": "id", "zsm": "zsm", "ces": "cs"}

log = logging.getLogger("concordance")

Line = tuple[str, int, str, str, str]


def shard(tag: str) -> int:
    """The number of the file a synset's sentences are in."""
    return int(tag[:8]) % SHARDS


def kwic(sent: Sentence, wids: list[int]) -> tuple[str, str, str]:
    """A sentence as what is before a concept's words, the words, and what is after.

    Args:
        sent: the sentence
        wids: the ids of the concept's words

    Returns:
        (left, keyword, right); the keyword runs from the concept's
        first word to its last, with any words between them.
    """
    glue = compute_nospace(sent.words, sent.text)
    at = [i for i, w in enumerate(sent.words) if w.wid in wids]
    if not at:
        return sent.text, "", ""
    parts = ["", "", ""]
    for i, word in enumerate(sent.words):
        part = 0 if i < at[0] else 1 if i <= at[-1] else 2
        parts[part] += word.word + ("" if glue[i] or i in (at[0] - 1, at[-1]) else " ")
    return parts[0].rstrip(), parts[1].strip(), parts[2].strip()


def read_lang(corpus_db: Path, lang: str, pages: Path) -> dict[str, list[Line]]:
    """The uses of each synset in one language's corpus.

    Args:
        corpus_db: the language's corpus database
        lang: the language
        pages: the directory of the language's document pages; a
            document with no page there is left out

    Returns:
        For each synset, (document, sentence id, left, keyword, right)
        for each use, in the corpus's order.
    """
    uses: dict[str, list[Line]] = defaultdict(list)
    con = db.connect(corpus_db)
    try:
        for (docid,) in con.execute("SELECT docid FROM doc ORDER BY docid").fetchall():
            doc = db.read_document(con, lang, docid)
            if not (pages / f"{doc.doc}-view.html").exists():
                continue
            for sent in doc.sentences:
                for concept in sent.concepts:
                    if concept.tag and SYNSET.fullmatch(concept.tag):
                        uses[concept.tag].append(
                            (doc.doc, sent.sid, *kwic(sent, concept.wids)))
    finally:
        con.close()
    return uses


def write_concordance(outdir: Path, dbdir: Path) -> Counter:
    """Write the concordance files for the languages that have pages.

    Args:
        outdir: the display directory
        dbdir: the directory of the corpus databases, LANG.db

    Returns:
        How many times each synset is used, in all the languages.
    """
    shards: list[dict] = [{} for _ in range(SHARDS)]
    total: Counter = Counter()
    for pages in sorted(p for p in outdir.iterdir() if (dbdir / f"{p.name}.db").exists()):
        lang = pages.name
        uses = read_lang(dbdir / f"{lang}.db", lang, pages)
        for tag, lines in uses.items():
            entry = shards[shard(tag)].setdefault(tag, {"n": {}, "x": {}})
            entry["n"][lang] = len(lines)
            entry["x"][lang] = lines[:CAP]
            total[tag] += len(lines)
        log.info("%s: %d synsets, %d uses", lang, len(uses), sum(map(len, uses.values())))
    conc = outdir / "data" / "conc"
    conc.mkdir(parents=True, exist_ok=True)
    for number, content in enumerate(shards):
        (conc / f"{number}.json").write_text(
            json.dumps(content, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return total


def ilis() -> dict[str, str]:
    """The ILI of each Princeton WordNet 3.0 synset, by the corpus's synset id."""
    out = {}
    for line in ILI_MAP.read_text().splitlines():
        ili, offset = line.split()
        out[offset] = ili
        if offset.endswith("s"):  # the corpus has satellites as -a
            out[offset[:-1] + "a"] = ili
    return out


def shared_ids() -> dict[str, str]:
    """The id in omw-ntumc of each synset of the corpus that is a shared concept.

    Returns:
        ``omw-ntumc-NNNNN-POS`` by the corpus's synset, from the
        registry (local id ntumcNNNNN); empty if the registry is not there.
    """
    if not REGISTRY.exists():
        log.warning("%s is missing: the shared concepts are not linked", REGISTRY)
        return {}
    with REGISTRY.open(newline="", encoding="utf-8") as f:
        return {row["ntumc_synset"]: f"omw-ntumc-{row['local_id'].removeprefix('ntumc')}-{row['pos']}"
                for row in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)}


def identified(lexicons: Path) -> dict[str, list[str]]:
    """The synsets that share a concept with each synset of the corpus, by dc:identifier.

    Our wordnets give a synset that has no ILI the identifier of its
    concept (``pronoun:1;Sg``, ``ntumc02262``), and the lexicon that
    holds the concept gives it the same one.

    Args:
        lexicons: a directory of WN-LMF files: the wordnets Cygnet was built from

    Returns:
        For a synset of the corpus that one of the files identifies, the
        ids of all the synsets with its identifier.
    """
    tag_ids: dict[str, set[str]] = defaultdict(set)
    members: dict[str, list[str]] = defaultdict(list)
    for path in sorted(lexicons.glob("*.xml")):
        with path.open(encoding="utf-8") as f:
            for line in f:
                if "<Synset " not in line or "dc:identifier=" not in line:
                    continue
                synset = re.search(r'\bid="([^"]+)"', line)
                identifier = re.search(r'dc:identifier="([^"]+)"', line)
                if not synset or not identifier:
                    continue
                members[identifier.group(1)].append(synset.group(1))
                tag = re.search(r"-(\d{8}-[a-z])$", synset.group(1))
                if tag:
                    tag_ids[tag.group(1)].add(identifier.group(1))
    return {tag: [m for i in sorted(ids) for m in members[i]] for tag, ids in tag_ids.items()}


def concepts(wordnet: Path, tags: list[str]) -> dict[str, int]:
    """Cygnet's concept for each synset of the corpus that it has.

    A synset with an ILI is found by it; another by its id in omw-ntumc
    or in one of our wordnets (LEXICON-SYNSET), or by the id of a synset
    with the same dc:identifier (a pronoun of omw-pronoun, say), in
    Cygnet's provenance.

    Args:
        wordnet: the web directory of the Cygnet build
        tags: the corpus's synsets

    Returns:
        The concept's row id for each synset found.
    """
    con = sqlite3.connect(f"file:{wordnet / 'cygnet.db'}?mode=ro", uri=True)
    by_ili = dict(con.execute("SELECT ili, rowid FROM synsets WHERE ili IS NOT NULL"))
    con.close()
    con = sqlite3.connect(f"file:{wordnet / 'provenance.db'}?mode=ro", uri=True)
    by_id = dict(con.execute(
        "SELECT p.original_id, p.item_rowid FROM provenance p "
        "JOIN prov_tables t ON t.rowid = p.table_rowid WHERE t.name = 'synsets'"))
    con.close()
    to_ili, shared = ilis(), shared_ids()
    raw = wordnet.parent / "bin" / "raw_wns"  # where Cygnet's build keeps its wordnets
    others = identified(raw) if raw.is_dir() else {}
    found = {}
    for tag in tags:
        rowid = by_ili.get(to_ili.get(tag, ""))
        if rowid is None:
            # a shared concept first: a wordnet's own synset may not be merged into it yet
            names = [shared.get(tag, "")] + others.get(tag, [])
            names += [f"{lex}-{tag}" for lex in LEXICONS]
            rowid = next((by_id[name] for name in names if name in by_id), None)
        if rowid is not None:
            found[tag] = rowid
    return found


def write_links(outdir: Path, wordnet: Path, total: Counter) -> dict[str, int]:
    """Write the two files that link the corpus's synsets and Cygnet's concepts.

    Returns:
        Cygnet's concept for each synset of the corpus that it has.
    """
    found = concepts(wordnet, sorted(total))
    (outdir / "data" / "wn-links.json").write_text(
        json.dumps(found, separators=(",", ":")), encoding="utf-8")
    index: dict[int, list] = {}
    for tag, rowid in found.items():  # two synsets of one concept: the more used is linked
        if rowid not in index or total[tag] > index[rowid][1]:
            index[rowid] = [tag, total[tag]]
    (wordnet / "corpus-index.json").write_text(
        json.dumps(index, separators=(",", ":")), encoding="utf-8")
    missing = [tag for tag in total if tag not in found]
    log.info("%d of %d synsets have a concept in Cygnet; %d uses are of the %d that do not",
             len(found), len(total), sum(total[t] for t in missing), len(missing))
    return found


def wordnet_data(wordnet: Path, lang: str, found: dict[str, int]) -> tuple[dict, dict]:
    """The definitions and the words of the corpus's synsets, from Cygnet.

    Args:
        wordnet: the web directory of the Cygnet build
        lang: Cygnet's code for the language
        found: Cygnet's concept for each synset of the corpus

    Returns:
        (definitions, words): for a synset, its definitions in the
        language joined by "; ", and its words in the order of their senses.
    """
    tags: dict[int, list[str]] = defaultdict(list)
    for tag, rowid in found.items():
        tags[rowid].append(tag)
    con = sqlite3.connect(f"file:{wordnet / 'cygnet.db'}?mode=ro", uri=True)
    defs: dict[str, str] = {}
    for rowid, text in con.execute(
            "SELECT d.synset_rowid, d.definition FROM definitions d "
            "JOIN languages l ON l.rowid = d.language_rowid "
            "WHERE l.code = ? AND d.definition != '' ORDER BY d.rowid", (lang,)):
        for tag in tags.get(rowid, []):
            defs[tag] = f"{defs[tag]}; {text}" if tag in defs else text
    words: dict[str, list[str]] = {}
    for rowid, form in con.execute(
            "SELECT s.synset_rowid, f.form FROM senses s "
            "JOIN entries e ON e.rowid = s.entry_rowid "
            "JOIN languages l ON l.rowid = e.language_rowid "
            "JOIN forms f ON f.entry_rowid = e.rowid "
            "WHERE l.code = ? AND f.rank = (SELECT MIN(rank) FROM forms WHERE entry_rowid = e.rowid) "
            "ORDER BY s.synset_rowid, s.sense_index, s.rowid", (lang,)):
        for tag in tags.get(rowid, []):
            if form not in words.setdefault(tag, []):
                words[tag].append(form)
    con.close()
    return defs, words


def same(word: str, lang: str = "") -> str:
    """A word as it is compared: lower case, spaces for underscores.

    Chinese and Japanese words are compared without their spaces.
    """
    return ("" if lang in ("cmn", "jpn") else " ").join(word.replace("_", " ").lower().split())


def write_wordnet_data(outdir: Path, wordnet: Path, found: dict[str, int]) -> list[tuple]:
    """Make the display's definitions and word lists again from Cygnet's wordnets.

    make_display.py writes data/wn-defs-LANG.json and wn-syns-LANG.json
    from the wordnet database.  For the languages of WN_LANGS they are
    written again from the Cygnet build.  A synset Cygnet has no concept
    for keeps what the file had, and so does a definition that the new
    wordnets lack; a word they lack is left out, since most were removed
    as wrong.

    Args:
        outdir: the display directory
        wordnet: the web directory of the Cygnet build
        found: Cygnet's concept for each synset of the corpus

    Returns:
        What the old files had that the new ones lack, as
        (language, synset, "definition" or "word", what is lost).
    """
    lost = []
    for lang, code in WN_LANGS.items():
        defs, words = wordnet_data(wordnet, code, found)
        for kind, new in (("defs", defs), ("syns", words)):
            path = outdir / "data" / f"wn-{kind}-{lang}.json"
            old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            for tag, was in old.items():
                if tag not in found:
                    new[tag] = was
                elif kind == "defs" and tag not in new:
                    lost.append((lang, tag, "definition", was))
                    new[tag] = was
                elif kind == "syns":
                    now = {same(w, lang) for w in new.get(tag, [])}
                    lost += [(lang, tag, "word", w) for w in was if same(w, lang) not in now]
            path.write_text(json.dumps(new, ensure_ascii=False, separators=(",", ":")),
                            encoding="utf-8")
            log.info("wn-%s-%s.json: %d synsets (were %d)", kind, lang, len(new), len(old))
    return lost


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--outdir", type=Path, default=ROOT / "display",
                        help="the display directory (default: display/)")
    parser.add_argument("--dbdir", type=Path, default=ROOT / "build",
                        help="the directory of the corpus databases (default: build/)")
    parser.add_argument("--wordnet", type=Path,
                        help="web directory of a Cygnet build, to link to")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    total = write_concordance(args.outdir, args.dbdir)
    log.info("%d synsets, %d uses in %s", len(total), sum(total.values()),
             args.outdir / "data" / "conc")
    if args.wordnet:
        found = write_links(args.outdir, args.wordnet, total)
        lost = write_wordnet_data(args.outdir, args.wordnet, found)
        with (args.outdir / "data" / "wn-lost.tsv").open("w", newline="", encoding="utf-8") as f:
            out = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_NONE, quotechar=None, escapechar="\\")
            out.writerow(["lang", "synset", "what", "lost"])
            out.writerows(lost)
        for (lang, what), n in sorted(Counter((row[0], row[2]) for row in lost).items()):
            log.info("%s: %d %ss of the wordnet database are not in the new wordnets", lang, n, what)
    page = _get_env().get_template("concept.html").render(base=".", shards=SHARDS, cap=CAP)
    (args.outdir / "concept.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
