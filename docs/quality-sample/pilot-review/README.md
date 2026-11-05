# Pilot of the calibrated review on never-flagged wnja senses (2026-11-07)

5,000 of the 141,564 wnja senses no audit had flagged (random, seed
20261107, spot-check items left out), reviewed blind twice by Claude
Sonnet with the `info` prompt of `../calibration/` (`PROMPT.md`), in 25
batches of 200 per run, under fresh ids and shuffles
(`scripts/pilot_review.py`).  `items.tsv` has what the reviewers saw;
`final.tsv` both verdicts and reasons and the decision.

| run 1 \ run 2 | OK | UNSURE | WRONG |
|---|---:|---:|---:|
| OK | 4,031 | 211 | 25 |
| UNSURE | 177 | 265 | 68 |
| WRONG | 27 | 60 | 136 |

## Decision

`decide` in the script:

| verdicts | action | senses | share |
|---|---|---:|---:|
| both OK | keep | 4,031 | 80.6% |
| both WRONG | remove | 136 | 2.7% |
| OK and UNSURE, or both UNSURE and the word is in JMdict | lower to 0.8, no person | 547 | 10.9% |
| anything else (OK and WRONG, WRONG and UNSURE, both UNSURE and not in JMdict) | lower to 0.5, queue for a person | 286 | 5.7% |

A first rule (anything not unanimous goes to a person) queued 833
(16.7%), which over all 141k would be about 24,000 senses.

The removals read as real errors, mostly a sense reached through an
ambiguous English word (守る *continue*, 口火 *spark plug*, 太陰暦 *moon*,
富む *Tom*, パイ *Proto-Indo-European*, 話す for animal sounds).  The
double UNSURE are mostly rare or odd forms (住居空間, 徒遣, 手風, 不結果)
that the reviewers could not place.

## A second company on the removals

The 136 removals were reviewed blind, alone, by OpenAI's Codex CLI
(`codex-remove.tsv`): first with gpt-5.6-sol at low effort (almost
certainly; see `../calibration/`), then with gpt-6.1-sol at high effort.

| Codex | WRONG | OK | UNSURE |
|---|---:|---:|---:|
| gpt-5.6-sol, low | 97 | 27 | 12 |
| gpt-6.1-sol, high | 107 | 18 | 11 |

The two Codex runs both say WRONG on 88.  gpt-6.1-sol's OKs are a mix:
some are plausible (救済 *rescue*, 摘出 *exposing wrongdoing*, 守る
*maintain*, 引取人 *guarantor*); some are form problems that the prompt,
which asks only about meaning, lets through (広々とした水面 and 憲法の州
are phrases); some look lenient (通勤学).  On the dev items it is nearly as
good a judge as Sonnet, so its OK or UNSURE is a reason for a person to
look.  Proposal: remove the 107 on which both Sonnet runs and gpt-6.1-sol
agree; queue the 29.

## Position in the batch

The items are shuffled, so any trend with position is the reviewer's.
In both runs the first fifth of each batch of 200 drew more WRONG (6.8%
and 6.6%, against 2.7–5.1% for the other fifths) and more UNSURE, and the
two runs agreed less there (87% against 88–91%).  The reviewer starts
strict and settles.  The two-run rule damps this, since an item rarely
falls early in both shuffles.  On the dev items (batches of 100, seven
runs) agreement with checker 1 falls slightly from the first third to the
last (82%, 82%, 79%), within noise, and the rate of good senses called
WRONG shows no trend.

## Human check

`../pilot-check/` is a blind sheet of 140 of these decisions (50 removed,
30 queued, 30 lowered to 0.8, 30 kept) for a native checker, to measure
how right each action is on senses no audit had flagged.  Nothing here has
been applied to wnja.
