# Full sense review of COW 1.0 and Wordnet Bahasa 1.3 (2026-10-24)

Every sense of COW 1.0 and of Wordnet Bahasa 1.3 (except Bahasa senses
marked hand-checked, `Y`, in `wn-msa-all.tab`) was reviewed in three
steps, by `scripts/triage_review.py`:

1. **Triage.** Claude Haiku judged each sense OK or SUSPECT, in batches of
   400, with instructions to flag anything in doubt (94% recall on known
   wnja errors in the pilot, `../haiku-pilot/`).  Some triage agents also
   asked Claude Opus for a second opinion on their batch through
   `claude -p`, unprompted; this only added flags.
2. **Double blind review.** Claude Opus judged each flagged sense OK,
   WRONG or UNSURE twice, in two different shuffles under random IDs,
   without the triage reason, and noted malformed lemmas (FORM) and words
   of the other variety of Malay (MS in wnb-id, ID in wnb-zsm).
3. **Adjudication.** A third Opus call saw both verdicts and reasons for
   the senses where the runs disagreed or were both UNSURE.

| | COW | wnb-id | wnb-zsm |
|---|---|---|---|
| Senses triaged | 109,045 | 94,528 | 81,757 |
| Flagged by triage | 9,850 | 26,165 | 19,053 |
| Runs agree (OK/WRONG) | 84.6% | 83.4% | 85.8% |
| Adjudicated | 1,520 | 4,345 | 2,714 |
| Final WRONG | 4,359 | 16,924 | 14,050 |
| Final OK | 5,370 | 8,023 | 4,828 |
| Final UNSURE | 121 | 1,218 | 175 |
| Form note from both runs | 1,142 FORM | 2,552 MS, 627 FORM | 413 ID, 208 FORM |

`<lang>-final.tsv` has one row per flagged sense: synset, word, the
Haiku reason, both Opus verdicts, the final verdict and action, who
decided (`both` or `adjudication`) and why, and the form notes given by
both runs (`note_both`) or only one (`note_one`).

The corrections built from these tables are in the release repositories:
`bond-lab/cow` and `bond-lab/Bahasa-Wordnet`, `corrections/senses.tsv`
(see their `corrections/README.md` for the rules).

## Rescue of excluded-source Chinese senses

After the corrections, 395 COW synsets had a definition but no senses,
although the NTU-MC wordnet had 1,313 candidate lemmas for them from
sources COW leaves out (BOW, SEW, Wiktionary).  They were reviewed in the
same way (steps 2 and 3, all flagged), by `scripts/cow_rescue.py`; the
runs agreed on 94%, and 1,078 senses judged OK and not malformed are
added back (`cmn-rescue-final.tsv`).
