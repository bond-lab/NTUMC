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
import sqlite3
import string
import sys
from collections import defaultdict

import wn.lmf


# ── CEDICT loading ──────────────────────────────────────────────────────

_XREF_PREFIXES = ("see ", "variant of ", "old variant of ",
                   "erhua variant of ")


def _is_xref_only(meaning):
    """True if a CEDICT meaning is only cross-references (e.g. 'see 芥蓝')."""
    defs = meaning.split("/")
    return all(
        any(d.strip().startswith(p) for p in _XREF_PREFIXES)
        or d.strip() == ""
        for d in defs
    )


def _reading_tags(meaning):
    """Classify a CEDICT meaning string into a set of tags.

    Tags: ``surname-only``, ``used-in-only``, ``abbrev-only``, ``xref-only``.
    A tag ending in ``-only`` means *all* real definitions fit that category.
    """
    defs = [d.strip() for d in meaning.split("/") if d.strip()]
    if not defs:
        return {"empty"}
    tags = set()
    if all(any(d.startswith(p) for p in _XREF_PREFIXES) for d in defs):
        tags.add("xref-only")
        return tags
    real = [d for d in defs if not any(d.startswith(p) for p in _XREF_PREFIXES)]
    if not real:
        tags.add("xref-only")
        return tags
    if all(d.startswith("surname ") for d in real):
        tags.add("surname-only")
    if all(d.lower().startswith("used in ") for d in real):
        tags.add("used-in-only")
    if all("abbr." in d.lower() for d in real):
        tags.add("abbrev-only")
    if all("(coll.)" in d for d in real):
        tags.add("coll-only")
    if all("(Tw)" in d or "Taiwan pr." in d for d in real):
        tags.add("tw-only")
    return tags


# Pattern for pronunciation notes like "Taiwan pr. [xxx]"
_PR_NOTE_RE = re.compile(
    r"(Taiwan|colloquial|Beijing|old|literary)\s+pr\.\s*\[([^\]]+)\]",
    re.IGNORECASE,
)


def load_cedict(path):
    """Parse a gzipped CEDICT file into lookup dicts.

    Returns:
        word2pinyins   dict[str, list[str]]  — whole-word → list of readings
        word2standalone dict[str, set[str]]  — readings with real definitions
        word2defs      dict[str, dict[str, list[str]]]
                       — word → {pinyin: [def1, def2, ...]} (real defs only)
        char2pinyin    dict[str, list[tuple[str, int]]]
                       — single char → [(pinyin, freq)] sorted desc by freq
        word2tags      dict[str, dict[str, set[str]]]
                       — word → {pinyin: {tag, ...}} from _reading_tags
        word2notes     dict[str, dict[str, list[tuple[str, str]]]]
                       — word → {pinyin: [(note_type, noted_pinyin), ...]}
                       e.g. {pinyin: [("Taiwan", "xue4")]}
    """
    exp = re.compile(r"^([^ ]+) ([^ ]+) \[(.*)\] /(.+)/")
    word2pinyins_set = defaultdict(set)
    word2standalone = defaultdict(set)
    word2defs = defaultdict(lambda: defaultdict(list))
    word2tags = defaultdict(lambda: defaultdict(set))
    word2notes = defaultdict(lambda: defaultdict(list))
    char_freq = defaultdict(lambda: defaultdict(int))

    with gzip.open(path, mode="rt", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            m = exp.match(line)
            if m is None:
                continue
            _traditional, simplified, pinyin, meaning = m.groups()
            pinyin = pinyin.replace("u:", "ü").lower()
            word2pinyins_set[simplified].add(pinyin)
            word2tags[simplified][pinyin] |= _reading_tags(meaning)
            # Extract pronunciation notes
            for note_m in _PR_NOTE_RE.finditer(meaning):
                note_type = note_m.group(1).capitalize()
                noted_py = note_m.group(2).replace("u:", "ü").lower()
                word2notes[simplified][pinyin].append((note_type, noted_py))
            if not _is_xref_only(meaning):
                word2standalone[simplified].add(pinyin)
                # Store individual real definitions
                for d in meaning.split("/"):
                    d = d.strip()
                    if d and not any(
                        d.startswith(p) for p in _XREF_PREFIXES
                    ):
                        word2defs[simplified][pinyin].append(d)
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
    return (word2pinyins, word2standalone, word2defs, char2pinyin,
            word2tags, word2notes)


# ── Pinyin lookup ───────────────────────────────────────────────────────

_WEAK_TAGS = frozenset({"surname-only", "used-in-only", "abbrev-only",
                        "xref-only", "coll-only", "tw-only"})


def get_pinyin(word, word2pinyins, word2standalone, char2pinyin, word2tags):
    """Look up pinyin for *word*.

    Returns a list of (pinyin_str, variety, notation) triples, or [] if
    unresolvable.  *notation* is normally ``"pinyin"`` but may carry an
    annotation like ``"pinyin; Taiwan"`` when a pronunciation note is present.

    When a word has multiple CEDICT readings, prefer those with real
    definitions (not just cross-references like "see ...").  Within the
    real readings, eliminate "weak" ones — readings whose only definitions
    are surnames, "used in …", or abbreviations.  For character-by-character
    assembly, use the most frequent compound reading.
    """
    readings = word2pinyins.get(word, [])

    if len(readings) == 1:
        return [(readings[0], "cedict")]

    if len(readings) > 1:
        # Prefer readings with real definitions (standalone)
        standalone = word2standalone.get(word, set())
        if standalone:
            real = sorted(standalone)
        else:
            real = readings

        if len(real) == 1:
            return [(real[0], "cedict")]

        if len(real) > 1:
            # Eliminate weak readings (surname-only, used-in-only, etc.)
            tags = word2tags.get(word, {})
            strong = [p for p in real
                      if not (tags.get(p, set()) & _WEAK_TAGS)]
            if len(strong) == 1:
                return [(strong[0], "cedict")]
            if len(strong) > 1:
                return [(p, "cedict-variant") for p in strong]
            # All readings are weak — keep them all
            return [(p, "cedict-variant") for p in real]

        return [(p, "cedict-variant") for p in readings]

    # Not in CEDICT as a whole word → assemble character-by-character
    # (uses compound-frequency ranking, which is already the default order)
    parts = []
    for ch in word:
        if ch in char2pinyin:
            parts.append(char2pinyin[ch][0][0])  # most frequent reading
        elif ch == " " or ch == "\u2423":         # space / open-box
            parts.append(ch)
        else:
            return []
    return [(" ".join(parts), "cedict-char")]


# ── Gloss-based disambiguation ─────────────────────────────────────────

STOPWORDS = frozenset(
    "a an the is are was were be been being to of in for on at by with from "
    "as or and not that this it its etc used one has have had do does did "
    "will would can could may might shall should about into over after before "
    "between through up down out off than very just also so some any all each "
    "every both few more most other no such only same but if when".split()
)


def _tokenize(text):
    """Lowercase, strip punctuation, remove stop words, rough stemming."""
    text = text.lower().translate(str.maketrans("", "", string.punctuation))
    words = set(text.split()) - STOPWORDS
    stemmed = set()
    for w in words:
        for suffix in (
            "tion", "sion", "ness", "ment", "ing", "ous", "ive",
            "ful", "less", "ly", "ed", "er", "est", "al", "ity",
        ):
            if w.endswith(suffix) and len(w) > len(suffix) + 2:
                w = w[: -len(suffix)]
                break
        stemmed.add(w)
    return stemmed


def _score_reading(cedict_defs, gloss):
    """Count content-word overlap between CEDICT definitions and a gloss."""
    cedict_tokens = set()
    for d in cedict_defs:
        cedict_tokens |= _tokenize(d)
    return len(cedict_tokens & _tokenize(gloss))


def load_glosses(db_path):
    """Load English synset glosses and lemmas from the NTU-MC database.

    Returns {synset_id: gloss_text} where gloss_text combines the
    definition and all English lemmas for the synset, giving the
    tokenizer more material to match against CEDICT definitions.
    """
    db = sqlite3.connect(db_path)
    glosses = {}
    for ss, d in db.execute(
        "SELECT synset, def FROM synset_def WHERE lang = 'eng'"
    ):
        glosses[ss] = d

    # Append English lemmas to gloss text
    for ss, lemma in db.execute(
        "SELECT s.synset, w.lemma FROM sense s "
        "JOIN word w ON s.wordid = w.wordid "
        "WHERE w.lang = 'eng'"
    ):
        if ss in glosses:
            glosses[ss] += " " + lemma

    db.close()
    return glosses


def _is_tone5_pair(pinyins):
    """True if *pinyins* (list of 2) differ only in tone-5 vs another tone."""
    if len(pinyins) != 2:
        return False
    a_s, b_s = pinyins[0].split(), pinyins[1].split()
    if len(a_s) != len(b_s):
        return False
    if re.sub(r"[1-5]", "", pinyins[0]) != re.sub(r"[1-5]", "", pinyins[1]):
        return False
    # Every differing syllable must involve tone 5
    for sa, sb in zip(a_s, b_s):
        if sa != sb and not ("5" in sa or "5" in sb):
            return False
    return True


def _have_same_meaning(pinyins, defs_by_reading):
    """True if all *pinyins* share overlapping CEDICT definitions.

    Returns True when both readings have real definitions and at least
    one definition appears under both readings (case-insensitive).
    """
    if len(pinyins) < 2:
        return False
    sets = []
    for py in pinyins:
        ds = defs_by_reading.get(py, [])
        if not ds:
            return False
        sets.append({d.lower() for d in ds})
    # Check pairwise overlap — all pairs must share at least one def
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            if not (sets[i] & sets[j]):
                return False
    return True


def disambiguate_variants(resource, word2defs, word2notes, glosses):
    """Resolve multi-reading pronunciations using several heuristics.

    Stages (applied in order to ``cedict-variant`` entries):

    1. **Gloss matching** — score each reading against synset English
       glosses; pick a clear winner (variety ``cedict-gloss``).
    2. **Tone-5 pairs** — if two readings differ only in neutral tone
       (tone 5) vs full tone, keep both (variety ``cedict``).
    3. **Same-meaning variants** — if two readings share overlapping
       CEDICT definitions, keep both (variety ``cedict``).
    4. **Taiwan cross-references** — if one reading's CEDICT entry
       contains "Taiwan pr. [other]", keep both and annotate the
       Taiwan reading with ``notation="Taiwan"``.
    5. **Pronunciation notes** — add notes from CEDICT (e.g. "Taiwan",
       "colloquial") to the ``notation`` field of remaining variants.

    Returns (resolved, unresolved, ambiguous_report).
    """
    resolved = 0
    unresolved = 0
    ambiguous_report = []

    for lexicon in resource["lexicons"]:
        prefix = lexicon["id"] + "-"
        for entry in lexicon["entries"]:
            prons = entry["lemma"].get("pronunciations", [])
            if not prons or "unresolved" not in prons[0].get("notation", ""):
                continue

            word = entry["lemma"]["writtenForm"]
            defs_by_reading = word2defs.get(word, {})
            pron_pinyins = [p["text"] for p in prons]

            # ── Stage 1: gloss matching ──
            synset_glosses = []
            for sense in entry.get("senses", []):
                ss_id = sense["synset"]
                bare = ss_id[len(prefix):] if ss_id.startswith(prefix) else ss_id
                if bare in glosses:
                    synset_glosses.append(glosses[bare])

            if synset_glosses and defs_by_reading:
                combined = " ".join(synset_glosses)
                scores = {py: _score_reading(defs_by_reading[py], combined)
                          for py in defs_by_reading}
                ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
                best_py, best_score = ranked[0]
                second_score = ranked[1][1] if len(ranked) > 1 else 0

                if best_score > 0 and best_score > second_score:
                    entry["lemma"]["pronunciations"] = [
                        _make_pron(best_py, "cedict-gloss")
                    ]
                    resolved += 1
                    continue

            # ── Stage 2: tone-5 pairs — keep both ──
            if _is_tone5_pair(pron_pinyins):
                notes = word2notes.get(word, {})
                new_prons = []
                for py in pron_pinyins:
                    pr_note = None
                    for note_type, _noted_py in notes.get(py, []):
                        pr_note = note_type
                        break
                    new_prons.append(_make_pron(py, "cedict", pr_note))
                entry["lemma"]["pronunciations"] = new_prons
                resolved += 1
                continue

            # ── Stage 3: same-meaning variants — keep both ──
            if defs_by_reading and _have_same_meaning(pron_pinyins,
                                                       defs_by_reading):
                notes = word2notes.get(word, {})
                new_prons = []
                for py in pron_pinyins:
                    pr_note = None
                    for note_type, _noted_py in notes.get(py, []):
                        pr_note = note_type
                        break
                    new_prons.append(_make_pron(py, "cedict", pr_note))
                entry["lemma"]["pronunciations"] = new_prons
                resolved += 1
                continue

            # ── Stage 4: Taiwan cross-references — keep both ──
            notes = word2notes.get(word, {})
            tw_pinyins = set()
            for py, note_list in notes.items():
                for note_type, noted_py in note_list:
                    if note_type == "Taiwan":
                        tw_pinyins.add(py)
            if tw_pinyins and len(pron_pinyins) >= 2:
                new_prons = []
                for py in pron_pinyins:
                    if py in tw_pinyins:
                        new_prons.append(_make_pron(py, "cedict", "Taiwan"))
                    else:
                        new_prons.append(_make_pron(py, "cedict"))
                entry["lemma"]["pronunciations"] = new_prons
                resolved += 1
                continue

            # ── Stage 5: add pronunciation notes to remaining variants ──
            notes = word2notes.get(word, {})
            new_prons = []
            for p in prons:
                py = p["text"]
                pr_note = None
                for note_type, _noted_py in notes.get(py, []):
                    pr_note = note_type
                    break
                new_prons.append(_make_pron(py, "cedict-variant", pr_note))
            entry["lemma"]["pronunciations"] = new_prons

            # Still unresolved
            unresolved += 1
            if defs_by_reading:
                scores = {py: _score_reading(defs_by_reading[py],
                                             " ".join(synset_glosses))
                          for py in defs_by_reading} if synset_glosses else {}
                ambiguous_report.append({
                    "word": word,
                    "readings": {
                        py: "; ".join(ds[:3])
                        for py, ds in defs_by_reading.items()
                    },
                    "scores": scores,
                    "glosses": synset_glosses[:3],
                })

    return resolved, unresolved, ambiguous_report


# ── Add pronunciations to resource ─────────────────────────────────────

def _is_segmented(form):
    """Check if a form is tagged as a word-segmentation variant."""
    for tag in form.get("tags", []):
        if tag.get("category") == "segmentation":
            return True
    return False


def _make_pron(text, variety, pr_note=None):
    """Build a pronunciation dict with the appropriate notation.

    Resolved readings (cedict, cedict-gloss) get no notation attribute.
    Character-by-character readings get ``notation="composed"``.
    Unresolved variants get ``notation="unresolved"``.
    Pronunciation notes (e.g. "Taiwan") replace other notation values.
    """
    notation = None
    if variety == "cedict-char":
        notation = "composed"
    elif variety == "cedict-variant":
        notation = "unresolved"
    if pr_note:
        notation = pr_note
    pron = {"text": text}
    if notation:
        pron["notation"] = notation
    return pron


def _add_pinyin_to_form(form, word2pinyins, word2standalone, char2pinyin,
                        word2tags):
    """Add pinyin to a single form/lemma dict. Returns True if modified."""
    if form.get("pronunciations"):
        return False
    if _is_segmented(form):
        return False
    word = form["writtenForm"]
    results = get_pinyin(word, word2pinyins, word2standalone, char2pinyin,
                         word2tags)
    if not results:
        return False
    form["pronunciations"] = [_make_pron(text, variety)
                              for text, variety in results]
    return True


def _fix_particle_lemma(entry):
    """Handle +的/+地 lemmas: strip '+', mark senses as non-lexicalized.

    Returns True if the entry was modified.
    """
    lemma = entry["lemma"]["writtenForm"]
    if "+的" not in lemma and "+地" not in lemma:
        return False
    entry["lemma"]["writtenForm"] = lemma.replace("+", "")
    for sense in entry.get("senses", []):
        sense["lexicalized"] = False
    return True


def add_pinyin(resource, word2pinyins, word2standalone, char2pinyin,
               word2tags):
    """Walk entries in *resource* and add pinyin where missing.

    Also normalizes +的/+地 lemmas and marks their senses as non-lexicalized.

    Skips forms tagged with ``<Tag category="segmentation">``.
    Returns (pinyin_modified, particle_modified) counts.
    """
    pinyin_modified = 0
    particle_modified = 0
    for lexicon in resource["lexicons"]:
        for entry in lexicon["entries"]:
            if _fix_particle_lemma(entry):
                particle_modified += 1
            changed = _add_pinyin_to_form(
                entry["lemma"], word2pinyins, word2standalone, char2pinyin,
                word2tags,
            )
            for form in entry.get("forms", []):
                changed |= _add_pinyin_to_form(
                    form, word2pinyins, word2standalone, char2pinyin,
                    word2tags,
                )
            if changed:
                pinyin_modified += 1
    return pinyin_modified, particle_modified


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
    parser.add_argument(
        "--db", default=None,
        help="Path to wn-ntumc.db for gloss-based pinyin disambiguation",
    )
    parser.add_argument(
        "--ambiguous", default=None,
        help="Write remaining ambiguous entries to TSV file",
    )
    args = parser.parse_args()

    output = args.output or args.wn_xml

    print(f"Loading CEDICT from {args.cedict_gz} …", file=sys.stderr)
    (word2pinyins, word2standalone, word2defs, char2pinyin,
     word2tags, word2notes) = load_cedict(args.cedict_gz)
    print(
        f"  {len(word2pinyins)} words, {len(char2pinyin)} characters",
        file=sys.stderr,
    )

    print(f"Loading wordnet from {args.wn_xml} …", file=sys.stderr)
    resource = wn.lmf.load(args.wn_xml, progress_handler=None)

    total_entries = sum(len(lx["entries"]) for lx in resource["lexicons"])
    pinyin_modified, particle_modified = add_pinyin(
        resource, word2pinyins, word2standalone, char2pinyin, word2tags
    )
    print(
        f"  Added pinyin to {pinyin_modified}/{total_entries} entries",
        file=sys.stderr,
    )
    if particle_modified:
        print(
            f"  Normalized {particle_modified} +的/+地 lemmas",
            file=sys.stderr,
        )

    # Gloss-based disambiguation of multi-reading entries
    if args.db:
        print("Disambiguating variants with English glosses …", file=sys.stderr)
        glosses = load_glosses(args.db)
        print(f"  {len(glosses)} English glosses loaded", file=sys.stderr)
        resolved, unresolved, report = disambiguate_variants(
            resource, word2defs, word2notes, glosses
        )
        print(
            f"  Resolved {resolved}, unresolved {unresolved}",
            file=sys.stderr,
        )
        if args.ambiguous and report:
            with open(args.ambiguous, "w", encoding="utf-8") as f:
                f.write("word\treading\tscore\tcedict_defs\twn_glosses\n")
                for item in sorted(report, key=lambda x: x["word"]):
                    wn_gloss = " | ".join(item["glosses"])
                    for py, score in sorted(
                        item["scores"].items(), key=lambda x: (-x[1], x[0])
                    ):
                        cedict_def = item["readings"].get(py, "")
                        f.write(
                            f"{item['word']}\t{py}\t{score}\t"
                            f"{cedict_def}\t{wn_gloss}\n"
                        )
            print(
                f"  Ambiguous entries written to {args.ambiguous}",
                file=sys.stderr,
            )

    print(f"Writing {output} …", file=sys.stderr)
    wn.lmf.dump(resource, output)
    print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
