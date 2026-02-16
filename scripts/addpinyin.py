#!/usr/bin/env python3
"""Add pinyin pronunciations to a Chinese WN-LMF wordnet using CEDICT.

Usage:
    addpinyin.py CEDICT_GZ WN_XML [--output WN_XML_OUT]

Reads a gzipped CEDICT dictionary and a WN-LMF XML file, then adds
<Pronunciation> elements (numbered-tone pinyin) to lemmas that lack them.

Pronunciation quality is encoded in the ``variety`` attribute:
  - cedict         exact unique CEDICT match
  - cedict-variant one of multiple CEDICT readings (all are added)
  - cedict-char    character-by-character assembly from CEDICT
"""

import argparse
import gzip
import re
import sys
from collections import defaultdict

import wn.lmf


# ── CEDICT loading ──────────────────────────────────────────────────────

def load_cedict(path):
    """Parse a gzipped CEDICT file into two lookup dicts.

    Returns:
        word2pinyins  dict[str, list[str]]  — whole-word → list of readings
        char2pinyin   dict[str, list[tuple[str, int]]]
                      — single char → [(pinyin, freq)] sorted desc by freq
    """
    exp = re.compile(r"^([^ ]+) ([^ ]+) \[(.*)\] /(.+)/")
    word2pinyins_set = defaultdict(set)
    char_freq = defaultdict(lambda: defaultdict(int))

    with gzip.open(path, mode="rt", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            m = exp.match(line)
            if m is None:
                continue
            _traditional, simplified, pinyin, _meaning = m.groups()
            pinyin = pinyin.replace("u:", "ü").lower()
            word2pinyins_set[simplified].add(pinyin)
            chars = list(simplified)
            sylls = pinyin.split()
            if len(chars) == len(sylls):
                for ch, sy in zip(chars, sylls):
                    char_freq[ch][sy] += 1

    # Convert sets → sorted lists, char freqs → sorted list of tuples
    word2pinyins = {w: sorted(ps) for w, ps in word2pinyins_set.items()}
    char2pinyin = {}
    for ch, freqs in char_freq.items():
        char2pinyin[ch] = sorted(
            ((py, f) for py, f in freqs.items()), key=lambda x: -x[1]
        )
    return word2pinyins, char2pinyin


# ── Pinyin lookup ───────────────────────────────────────────────────────

def get_pinyin(word, word2pinyins, char2pinyin):
    """Look up pinyin for *word*.

    Returns a list of (pinyin_str, variety) pairs, or [] if unresolvable.
    """
    readings = word2pinyins.get(word, [])

    if len(readings) == 1:
        return [(readings[0], "cedict")]

    if len(readings) > 1:
        return [(p, "cedict-variant") for p in readings]

    # Not in CEDICT as a whole word → assemble character-by-character
    parts = []
    for ch in word:
        if ch in char2pinyin:
            parts.append(char2pinyin[ch][0][0])  # most frequent reading
        elif ch == " " or ch == "\u2423":         # space / open-box
            parts.append(ch)
        else:
            return []
    return [(" ".join(parts), "cedict-char")]


# ── Add pronunciations to resource ─────────────────────────────────────

def _is_segmented(form):
    """Check if a form is tagged as a word-segmentation variant."""
    for tag in form.get("tags", []):
        if tag.get("category") == "segmentation":
            return True
    return False


def _add_pinyin_to_form(form, word2pinyins, char2pinyin):
    """Add pinyin to a single form/lemma dict. Returns True if modified."""
    if form.get("pronunciations"):
        return False
    if _is_segmented(form):
        return False
    word = form["writtenForm"]
    results = get_pinyin(word, word2pinyins, char2pinyin)
    if not results:
        return False
    form["pronunciations"] = [
        {"text": text, "notation": "pinyin", "variety": variety}
        for text, variety in results
    ]
    return True


def add_pinyin(resource, word2pinyins, char2pinyin):
    """Walk entries in *resource* and add pinyin where missing.

    Skips forms tagged with ``<Tag category="segmentation">``.
    Returns the number of entries modified.
    """
    modified = 0
    for lexicon in resource["lexicons"]:
        for entry in lexicon["entries"]:
            changed = _add_pinyin_to_form(
                entry["lemma"], word2pinyins, char2pinyin
            )
            for form in entry.get("forms", []):
                changed |= _add_pinyin_to_form(
                    form, word2pinyins, char2pinyin
                )
            if changed:
                modified += 1
    return modified


# ── CLI ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Add pinyin pronunciations to a Chinese WN-LMF file."
    )
    parser.add_argument("cedict_gz", help="Path to gzipped CEDICT file")
    parser.add_argument("wn_xml", help="Path to WN-LMF XML file")
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output XML path (default: overwrite input)",
    )
    args = parser.parse_args()

    output = args.output or args.wn_xml

    print(f"Loading CEDICT from {args.cedict_gz} …", file=sys.stderr)
    word2pinyins, char2pinyin = load_cedict(args.cedict_gz)
    print(
        f"  {len(word2pinyins)} words, {len(char2pinyin)} characters",
        file=sys.stderr,
    )

    print(f"Loading wordnet from {args.wn_xml} …", file=sys.stderr)
    resource = wn.lmf.load(args.wn_xml, progress_handler=None)

    total_entries = sum(len(lx["entries"]) for lx in resource["lexicons"])
    modified = add_pinyin(resource, word2pinyins, char2pinyin)
    print(
        f"  Added pinyin to {modified}/{total_entries} entries",
        file=sys.stderr,
    )

    print(f"Writing {output} …", file=sys.stderr)
    wn.lmf.dump(resource, output)
    print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
