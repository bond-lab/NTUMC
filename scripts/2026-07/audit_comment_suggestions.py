#!/usr/bin/env python3
"""Triage annotator suggestions left in concept comments.

Many concept comments carry actionable suggestions in a semi-structured
notation:

    =SYNSET     tag this concept with SYNSET (adding the lemma if needed)
    <SYNSET     create a new synset under SYNSET, then tag with it
    ~SYNSET     create/use a synset related to SYNSET
    lemma=X     the (new) lemma should be X

This script cross-checks every such suggestion against the current
wordnet (wn-ntumc.db) and the concept's current tag, and classifies it:

    DONE       concept is tagged as suggested — comment can be retired
    PARTLY     wordnet has the suggested entry, corpus not retagged —
               mechanically fixable
    TODO       nothing done yet (suggested synset lacks the lemma, or no
               linked synset with the lemma exists)
    STALE      referenced synset does not exist in the wordnet
    MISMATCH   concept carries a different real synset — resolved
               differently or a bad suggestion; needs a human
    FREETEXT   unstructured suggestion — needs a human (or LLM) pass

Read-only: writes a TSV for review plus a summary, changes no data.

Usage:
    .venv/bin/python scripts/2026-07/audit_comment_suggestions.py \
        [--out docs/comment-suggestions.tsv]
"""

import argparse
import logging
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BUILD = Path(__file__).resolve().parents[2] / "build"
LANGS = ["eng", "cmn", "jpn", "ind", "ita", "ces"]
PLACEHOLDER_TAGS = {None, "", "x", "w", "e", "u", "m", "s", "p",
                    "nam", "per", "org", "dat", "num", "oth"}

SYNSET_RE = re.compile(r"([=<>~])?\s*(\d{8}-[nvarzx])")
LEMMA_RE = re.compile(r"[Ll]emma\s*[=:]\s*([^\s;,]+)")

# Comments matching any of these are annotation notes, not suggestions.
BOILERPLATE = re.compile(
    r"pronoun \(|closed class|Not an open class|^preposition\W*$"
    r"|^auxiliary verb\W*$|^determiner\W*$|^xtrans; None$|^None$"
    r"|^\s*$")

# Free-text phrases that signal an actionable suggestion.
FREETEXT_CUES = re.compile(
    r"add|creat|new synset|should be|missing|tag(ged)? together"
    r"|tokenis|tokeniz|Def:|Link:", re.IGNORECASE)


def norm(lemma: str) -> str:
    """Normalise a lemma for wordnet comparison."""
    return lemma.replace("_", " ").replace("+", " ").strip().lower()


class WordNet:
    """Lemma/synset lookups over wn-ntumc.db."""

    def __init__(self, db_path: Path) -> None:
        """Index synset membership and inter-synset links per language."""
        conn = sqlite3.connect(str(db_path))
        self.synsets: set[str] = {
            r[0] for r in conn.execute("SELECT DISTINCT synset FROM synset")}
        # (lang, norm lemma) -> {synset}
        self.by_lemma: dict[tuple[str, str], set[str]] = defaultdict(set)
        for synset, lang, lemma in conn.execute(
                "SELECT s.synset, s.lang, w.lemma FROM sense s "
                "JOIN word w ON w.wordid = s.wordid"):
            self.by_lemma[(lang, norm(lemma or ""))].add(synset)
        self.links: dict[str, set[str]] = defaultdict(set)
        for s1, s2 in conn.execute("SELECT synset1, synset2 FROM synlink"):
            self.links[s1].add(s2)
            self.links[s2].add(s1)
        conn.close()

    def lemma_synsets(self, lang: str, lemma: str) -> set[str]:
        """Synsets containing this lemma in this language."""
        return self.by_lemma.get((lang, norm(lemma)), set())

    def linked_with_lemma(self, lang: str, lemma: str,
                          target: str) -> set[str]:
        """Synsets containing the lemma that link to the target synset."""
        return {s for s in self.lemma_synsets(lang, lemma)
                if target in self.links.get(s, set())}


def classify(op: str, target: str, tag: str | None, lang: str,
             lemmas: list[str], wn: WordNet) -> tuple[str, str]:
    """Classify one structured suggestion.

    Args:
        op: The operator ('=', '<', '~', or '' for a bare reference).
        target: The referenced synset id.
        tag: The concept's current tag.
        lang: Corpus language.
        lemmas: Candidate lemmas (suggested lemma first, then clemma).
        wn: Wordnet index.

    Returns:
        (classification, detail) — detail names the synset that
        satisfies the suggestion where one exists.
    """
    if target not in wn.synsets:
        return "STALE", "synset not in wn-ntumc"
    if op in ("=", ""):
        if tag == target:
            return "DONE", "tagged as suggested"
        in_wn = any(target in wn.lemma_synsets(lang, x) for x in lemmas)
        if tag in PLACEHOLDER_TAGS:
            if in_wn:
                return "PARTLY", "lemma in synset, corpus not retagged"
            return "TODO", "lemma not in suggested synset"
        return "MISMATCH", f"tagged {tag} instead"
    # '<' and '~': a new synset linked to the target should now exist;
    # tagging the referenced synset itself also settles the suggestion
    if tag == target:
        return "DONE", "tagged with the referenced synset"
    for lemma in lemmas:
        hits = wn.linked_with_lemma(lang, lemma, target)
        if tag in hits:
            return "DONE", f"tagged {tag}, linked to {target}"
        if hits:
            if tag in PLACEHOLDER_TAGS:
                return "PARTLY", f"synset {sorted(hits)[0]} exists, " \
                                 "corpus not retagged"
            return "MISMATCH", f"tagged {tag}; candidate {sorted(hits)[0]}"
    if tag not in PLACEHOLDER_TAGS:
        return "MISMATCH", f"tagged {tag}, no linked synset with lemma"
    return "TODO", "no linked synset with lemma"


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Classify annotator suggestions in concept comments.")
    parser.add_argument("--out", type=Path,
                        default=Path("docs/comment-suggestions.tsv"))
    args = parser.parse_args()

    wn = WordNet(BUILD / "wn-ntumc.db")
    logger.info("wordnet loaded: %d synsets", len(wn.synsets))

    rows: list[tuple] = []
    counts: Counter = Counter()
    for lang in LANGS:
        db = BUILD / f"{lang}.db"
        if not db.exists():
            continue
        conn = sqlite3.connect(str(db))
        for sid, cid, clemma, tag, comment in conn.execute(
                "SELECT sid, cid, clemma, tag, comment FROM concept "
                "WHERE comment IS NOT NULL AND comment != ''"):
            comment = str(comment)
            if "BAD[" in comment:
                # suggestion reviewed and rejected (mark_bad_suggestions.py)
                counts[lang, "REJECTED"] += 1
                continue
            if BOILERPLATE.search(comment) and not SYNSET_RE.search(comment):
                counts[lang, "boilerplate"] += 1
                continue
            refs = SYNSET_RE.findall(comment)
            lemma_m = LEMMA_RE.search(comment)
            lemmas = [lemma_m.group(1)] if lemma_m else []
            if clemma:
                lemmas.append(str(clemma))
            if refs:
                # a comment may repeat the same reference; report it once
                refs = list(dict.fromkeys(refs))
                for op, target in refs:
                    cls, detail = classify(op or "=", target, tag, lang,
                                           lemmas, wn)
                    counts[lang, cls] += 1
                    rows.append((lang, sid, cid, clemma, tag or "",
                                 (op or "=") + target, cls, detail,
                                 comment.replace("\t", " ")
                                        .replace("\n", " ")[:300]))
            elif FREETEXT_CUES.search(comment):
                counts[lang, "FREETEXT"] += 1
                rows.append((lang, sid, cid, clemma, tag or "", "",
                             "FREETEXT", "",
                             comment.replace("\t", " ")
                                    .replace("\n", " ")[:300]))
            else:
                counts[lang, "other-note"] += 1
        conn.close()
        logger.info("%s scanned", lang)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("lang\tsid\tcid\tclemma\ttag\tsuggestion\tclass\t"
                 "detail\tcomment\n")
        for r in sorted(rows, key=lambda r: (r[0], r[6], r[1], r[2])):
            fh.write("\t".join(str(x) for x in r) + "\n")
    logger.info("wrote %d rows to %s", len(rows), args.out)

    print("\nSummary per suggestion reference (per language):")
    classes = ["DONE", "PARTLY", "TODO", "MISMATCH", "STALE", "FREETEXT",
               "REJECTED", "other-note", "boilerplate"]
    print(f"{'lang':<6}" + "".join(f"{c:>12}" for c in classes))
    for lang in LANGS:
        line = f"{lang:<6}"
        for c in classes:
            line += f"{counts.get((lang, c), 0):>12}"
        print(line)

    # concept-level rollup: a comment naming several synsets is DONE as
    # soon as one of them is satisfied
    rank = {c: i for i, c in enumerate(
        ["DONE", "PARTLY", "MISMATCH", "TODO", "STALE", "FREETEXT"])}
    best: dict[tuple, str] = {}
    for r in rows:
        key = (r[0], r[1], r[2])
        cls = r[6]
        if key not in best or rank[cls] < rank[best[key]]:
            best[key] = cls
    rollup: Counter = Counter()
    for (lang, _, _), cls in best.items():
        rollup[lang, cls] += 1
    print("\nSummary per concept (best reference wins):")
    classes = ["DONE", "PARTLY", "TODO", "MISMATCH", "STALE", "FREETEXT"]
    print(f"{'lang':<6}" + "".join(f"{c:>12}" for c in classes))
    for lang in LANGS:
        line = f"{lang:<6}"
        for c in classes:
            line += f"{rollup.get((lang, c), 0):>12}"
        print(line)


if __name__ == "__main__":
    main()
