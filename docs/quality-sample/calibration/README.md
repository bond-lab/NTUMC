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

`<prompt>/PROMPT.md` is the prompt, `review.tsv` the verdicts and `key.tsv`
the id → spot-check item map.
