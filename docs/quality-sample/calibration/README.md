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

## A reviewer from another company: Codex

Blind runs of the info prompt by OpenAI's Codex CLI, in the same three
batches of about 100, each in a directory holding only the prompt and the
batch (2026-11-05).  `info-codex` was Codex 0.144.1 with its defaults, run
ephemeral so the model was not recorded; it was almost certainly
gpt-5.6-sol at low reasoning effort (that version's default, and its
reasoning used only 100-2,000 tokens a batch).  `info-codex61` is Codex
0.166.0 with gpt-6.1-sol at high effort, set explicitly.

| run | agreement | κ (checker 1) | κ (checker 2) | WRONG recall | UNSURE | good called WRONG |
|---|---|---|---|---|---|---|
| info, Codex gpt-5.6-sol (low) | 0.791 | 0.52 | 0.51 | 0.80 | 19 | 41 |
| info, Codex gpt-6.1-sol (high) | 0.822 | 0.59 | 0.60 | 0.85 | 12 | 37 |

gpt-6.1-sol at high effort is nearly as good a judge as Sonnet (κ 0.59
against 0.62) but rarely says UNSURE, so it calls more good senses WRONG.
Its errors are partly different: it gives the same verdict as the first
Sonnet info run on 79% of items, where the second Sonnet run gives the
same on 86%.  Under the two-run rule, with the first Sonnet run:

| pair | keep | lower | queue | remove | removed, OK by checker 1 |
|---|---:|---:|---:|---:|---:|
| Sonnet + Sonnet | 137 | 53 | 20 | 80 | 26 |
| Sonnet + Codex gpt-5.6-sol | 140 | 36 | 41 | 73 | 22 |
| Sonnet + Codex gpt-6.1-sol | 145 | 31 | 38 | 76 | 23 |

So a second company buys slightly more precise removals for a longer
queue; on the 136 pilot removals it is more useful as a filter (see
`../pilot-review/`).

## After the second look

The first checker then looked again at the 21 items where they and all
four prompts differed (`../spot-check/second-look/`), and changed 6 of
their answers to the models' and 2 to UNSURE.  `score.tsv` now uses
those answers; the tables above are against the blind first answers.

| condition | agreement | κ (checker 1) | good called WRONG | WRONG precision |
|---|---:|---:|---:|---:|
| strict | 0.814 | 0.59 | 40 | 0.61 |
| human | 0.859 | 0.68 | 26 | 0.68 |
| info | 0.870 | 0.70 | 25 | 0.70 |
| guided | 0.836 | 0.63 | 35 | 0.65 |
| info, second run | 0.861 | 0.69 | 27 | 0.69 |
| info, Opus | 0.798 | 0.59 | 47 | 0.59 |
| info, Codex gpt-5.6-sol (low) | 0.812 | 0.57 | 36 | 0.62 |
| info, Codex gpt-6.1-sol (high) | 0.851 | 0.66 | 31 | 0.68 |

Every condition gains about 0.05-0.08 κ and the ranking is unchanged.
The gain is an upper bound: only items where the models all disagreed
with the checker were looked at again, and the checker saw the models'
answers, so errors the checker and the models share are still in the
labels.  Under the two-run rule, two Sonnet info runs now remove 80 (20 OK
by checker 1) and Sonnet with Codex gpt-6.1-sol 76 (17 OK); both keep 3
senses the checker judged WRONG.

`<prompt>/PROMPT.md` is the prompt, `review.tsv` the verdicts and `key.tsv`
the id → spot-check item map.
