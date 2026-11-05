# Pilot of the calibrated review on never-flagged wnja senses (2026-11-07)

5,000 of the 141,564 wnja senses no audit had flagged (random, seed
20261107, spot-check items left out), reviewed blind twice by Claude
Sonnet with the `info` prompt of `../calibration/` (`PROMPT.md`), in 25
batches of 200 per run, under fresh ids and shuffles
(`scripts/pilot_review.py`).  `items.tsv` has what the reviewers saw;
`final.tsv` both verdicts and reasons and the decision.

| run 1 \ run 2 | OK | UNSURE | WRONG |
|---|---|---|---|
| OK | 4,031 | 211 | (27 OK/WRONG in all) |
| UNSURE | 177 | 265 | 68 |
| WRONG | 27 | 60 | 136 |

Decision: remove if both WRONG (136, 2.7%), keep if both OK (4,031,
80.6%), otherwise lower and queue for a person (833, 16.7%).

The removals read as real errors, mostly a sense reached through an
ambiguous English word (守る *continue*, 口火 *spark plug*, 太陰暦 *moon*,
富む *Tom*, パイ *Proto-Indo-European*, 話す for animal sounds).  The
double UNSURE are mostly rare or odd forms (住居空間, 徒遣, 手風, 不結果)
that the reviewers could not place.  Nothing here has been checked by a
person yet, and nothing has been applied to wnja.
