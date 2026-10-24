# Review of Wordnet Bahasa's Indonesian definitions (2026-10-25)

All 13,101 Indonesian definitions of wnb-id 1.5 (before this review) were
judged by `scripts/def_review.py`: two blind Claude Opus runs, in
different shuffles under random ids, rated each definition against the
English synset as OK, PARTIAL (right concept, but vague, truncated,
clumsy or with English words), WRONG (another concept, garbled, not a
definition) or UNSURE, and suggested a rewrite for PARTIAL and WRONG.  An
Opus adjudicator decided the 1,358 where the runs disagreed (89.6%
agreed; nearly all disagreements were OK against PARTIAL).

| Final | Definitions | On synsets with words | Without words |
|---|---|---|---|
| OK | 7,913 | 5,673 | 2,240 |
| PARTIAL | 4,426 | 3,005 | 1,421 |
| WRONG | 761 | 533 | 228 |
| UNSURE | 1 | 0 | 1 |

In Wordnet Bahasa 1.5 (`corrections/definitions.tsv`) WRONG definitions
are removed and PARTIAL ones kept with confidence 0.5 and the reason as
a note.  The suggested rewrites (`id-suggestions-pending.tsv`) are not
applied: model-written text waits for a human check.

`id-final.tsv` has one row per definition: the final verdict, who decided,
the reason and suggestion, and both runs' verdicts and suggestions.
