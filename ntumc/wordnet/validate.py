"""Check a WN-LMF file with the validation of the wn module.

    from ntumc.wordnet import validate
    if not validate.check(Path("release/cow-1.2.xml")):
        sys.exit(1)

wn reports errors (codes beginning ``E``: an id used twice, a sense or a
relation whose synset is missing) and warnings (``W``: an empty synset,
a relation with no reverse, ...).  A release stops for an error, and
for the warnings in ``FAIL``; the other warnings are counted in the log.

Three warnings stop a release: ``W302``, an ILI on more than one synset
(an ILI names one concept); ``W202``, a word twice in a synset; and
``W203``, two entries for one written form in a synset.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

FAIL = ("E", "W202", "W203", "W302")  # a code, or the letter that begins it

log = logging.getLogger(__name__)


def report(xml: Path) -> dict[str, tuple[str, list[str]]]:
    """Run wn's checks on every lexicon in a file.

    Args:
        xml: a WN-LMF file

    Returns:
        For each check that found something: its code, with its message
        and what it found (lexicon id and the id of the entry, sense or
        synset), in the order found

    Raises:
        ImportError: if wn is not installed
    """
    from wn import lmf, validate  # here, so the package does not need wn

    found: dict[str, tuple[str, list[str]]] = {}
    for lexicon in lmf.load(xml, progress_handler=None)["lexicons"]:
        for code, result in validate.validate(lexicon, progress_handler=None).items():
            if result["items"]:
                ids = found.setdefault(code, (result["message"], []))[1]
                ids += [f"{lexicon['id']}: {item}" for item in result["items"]]
    return found


def check(xml: Path, fail: Sequence[str] = FAIL, show: int = 10) -> bool:
    """Validate a file with wn and log what it finds.

    Args:
        xml: a WN-LMF file
        fail: the codes that make the file unfit to release, each a
            code (``W302``) or the letter that begins it (``E``)
        show: how many of the things found to list for such a code

    Returns:
        False if a check in ``fail`` found something; True otherwise,
        and if wn is not installed (which is logged)
    """
    try:
        found = report(xml)
    except ImportError:
        log.warning("%s not validated: the wn module is not installed", xml.name)
        return True
    good = True
    for code, (message, ids) in sorted(found.items()):
        if code in fail or code[0] in fail:
            good = False
            log.error("%s: %s %s (%d): %s%s", xml.name, code, message, len(ids),
                      "; ".join(ids[:show]), " ..." if len(ids) > show else "")
        else:
            log.info("%s: %s %s (%d)", xml.name, code, message, len(ids))
    return good
