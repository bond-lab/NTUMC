# Opus review of all wnja 2.0 senses flagged in wnja issue #8

All 4,193 senses still in wnja 2.0 that the issue #8 audit (Claude Sonnet
4.6) flagged were reviewed blind by Claude Opus: shuffled under random IDs
(`key.tsv`), 28 batches of about 150 (`batchNN.tsv`, `batchNN-review.tsv`),
without the audit's flag or the JMdict support.

`verdicts.tsv` combines them: synset, lemma, issue #8 flag, JMdict
support (see `../wnja-blind/README.md`), Opus verdict and reason, and the
proposed action (remove = WRONG, keep = OK, lower = UNSURE or not reviewed).

| Opus | Senses | Action |
|---|---|---|
| WRONG | 2,193 | remove |
| OK | 1,750 | keep (report back to issue #8) |
| UNSURE / missing | 250 | lower confidence |

On the 299 senses also reviewed blind by Sonnet, the two models agree on
74% (OK/WRONG split on 21 of 236 decisive pairs); in those 21 Opus was
usually right (e.g. 針鼠 hedgehog vs porcupine, 精液 semen vs sperm
cell; 風袋 'appearance' and 本塁 'main fortress' correctly kept).
