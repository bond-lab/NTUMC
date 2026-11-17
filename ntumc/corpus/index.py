"""An index of the ids seen in a stream of documents, for resolving links."""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import ConceptLink, Document, SentLink, WordLink


@dataclass
class Index:
    """Per language: the docids, and per sentence its wids, cids and xids.

    Built up as documents stream past, so that the alignments that
    follow can be checked without holding the documents.
    """

    docs: dict[tuple[str, int], str] = field(default_factory=dict)
    wids: dict[tuple[str, int], frozenset[int]] = field(default_factory=dict)
    cids: dict[tuple[str, int], frozenset[int]] = field(default_factory=dict)
    xids: dict[tuple[str, int], frozenset[int]] = field(default_factory=dict)

    def add(self, doc: Document) -> list[str]:
        """Record a document.

        Args:
            doc: the document

        Returns:
            Messages about ids that were already recorded
        """
        dups = []
        key = (doc.language, doc.docid)
        if key in self.docs:
            dups.append(f"{doc.language} d{doc.docid}: docid seen before")
        self.docs[key] = doc.doc
        for s in doc.sentences:
            skey = (doc.language, s.sid)
            if skey in self.wids:
                dups.append(f"{doc.language} s{s.sid}: sid seen before")
            self.wids[skey] = frozenset(w.wid for w in s.words)
            self.cids[skey] = frozenset(c.cid for c in s.concepts)
            self.xids[skey] = frozenset(x.xid for x in s.chunks)
        return dups

    def has_sent(self, lang: str, sid: int) -> bool:
        """True if the sentence was recorded."""
        return (lang, sid) in self.wids

    def has_word(self, lang: str, sid: int, wid: int) -> bool:
        """True if the word was recorded."""
        return wid in self.wids.get((lang, sid), ())

    def has_concept(self, lang: str, sid: int, cid: int) -> bool:
        """True if the concept was recorded."""
        return cid in self.cids.get((lang, sid), ())

    def has_link(
        self, flang: str, tlang: str, link: SentLink | WordLink | ConceptLink
    ) -> bool:
        """True if both ends of a link were recorded.

        Args:
            flang: from language
            tlang: to language
            link: the link

        Returns:
            Whether both ends exist
        """
        if isinstance(link, SentLink):
            return self.has_sent(flang, link.fsid) and self.has_sent(tlang, link.tsid)
        if isinstance(link, WordLink):
            return self.has_word(flang, link.fsid, link.fwid) and self.has_word(
                tlang, link.tsid, link.twid
            )
        return self.has_concept(flang, link.fsid, link.fcid) and self.has_concept(
            tlang, link.tsid, link.tcid
        )
