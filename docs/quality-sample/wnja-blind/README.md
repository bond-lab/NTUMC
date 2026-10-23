# Blind check of the wnja 2.0 senses flagged in wnja issue #8

Senses flagged as wrong by the issue #8 LLM audit (remaining in 2.0) were
split by multilingual JMdict support (glosses in de, nl, fr, es, sv, sl,
hu, ru matched against those languages' wordnets by ILI):

* A: in JMdict, no support in any language (1,504 senses)
* B: supported in 2+ non-English languages (482)
* C: other flagged senses (2,207)

100 senses were drawn from each group (seed 20261024), shuffled together
under random IDs (`key.tsv`, not shown to the reviewers) and reviewed
blind by three Claude Sonnet reviewers (`batch?.tsv`, `batch?-review.tsv`).

| Group | OK | WRONG | UNSURE |
|---|---|---|---|
| A | 35 | 48 | 17 |
| B | 52 | 29 | 18 |
| C | 38 | 49 | 13 |

Multilingual support helps somewhat (B) but does not separate good from
bad well enough to remove or keep whole groups; absence of support (A)
is no worse than C.  Both the audit and the reviewers are Sonnet, so
their agreement is not fully independent.
