# Calibrating the sense-review prompt (2026-11-06)

The 290 wnja spot-check items, with the first native checker's answers,
judged blind by Claude Sonnet under four prompts (one run each, fresh ids
and shuffle; `scripts/prompt_calibration.py`).  These items are now
development data (see `../spot-check/README.md`).

| prompt | definite | agreement | κ (checker 1) | κ (checker 2, 50) | WRONG precision | WRONG recall | UNSURE | good called WRONG |
|---|---|---|---|---|---|---|---|---|
| strict: correct translation? | 265 | 0.785 | 0.52 | 0.65 | 0.56 | 0.84 | 17 | 46 |
| human: the checkers' instructions | 229 | 0.825 | 0.60 | 0.80 | 0.61 | 0.86 | 53 | 32 |
| info: human + readings, JMdict, other senses, hypernyms, example | 232 | 0.836 | 0.62 | 0.60 | 0.64 | 0.89 | 50 | 31 |
| guided: info + guidance, fewer UNSURE | 270 | 0.807 | 0.56 | 0.62 | 0.59 | 0.85 | 12 | 41 |

The two checkers agree with κ = 0.54 on their 50 shared items, so every
prompt is at about the level of a second human.  The checkers' wording
calls about 30% fewer good senses WRONG than the strict question, at the
price of more UNSURE; the extra context helps a little more; pushing the
model to decide (guided) brings back false WRONGs.  With about 230–270
items, differences of 2–4 points are within noise.

On 22 items all four prompts disagree with checker 1.  Of the 17 the
checker accepted, most look like checker slips (電子ブック *exabyte*, 坊さん
*boy*, 競り売り *peddler*, "up to で、まで"), so
part of the measured disagreement is noise in the gold labels; these 22
should go back to the checkers before the labels are used further.

## Repeat runs and Opus

| run | agreement | κ (checker 1) | κ (checker 2) | WRONG recall | UNSURE | good called WRONG |
|---|---|---|---|---|---|---|
| human, second run | 0.815 | 0.59 | 0.60 | 0.87 | 49 | 35 |
| info, second run | 0.828 | 0.62 | 0.74 | 0.89 | 49 | 33 |
| info, Claude Opus | 0.776 | 0.54 | 0.51 | 0.94 | 37 | 51 |

Sonnet with the info prompt is stable: the two runs give identical
verdicts on 86% of items, with two OK/WRONG flips, and the same κ.  Opus
with the same prompt is stricter: it finds a few more of the checker's
WRONGs but calls 51 good senses WRONG against Sonnet's 31–33 (and flips 8
items against either Sonnet run).  The two-run rule (remove if both say
WRONG, keep if both say OK, otherwise lower and send to a person) with the
two Sonnet info runs removes 78 (26 of them OK by checker 1), keeps 134
(5 WRONG by checker 1) and sends 70 to a person; some of the 26 are
checker slips (see `../spot-check/second-look/`).

`<prompt>/PROMPT.md` is the prompt, `review.tsv` the verdicts and `key.tsv`
the id → spot-check item map.
