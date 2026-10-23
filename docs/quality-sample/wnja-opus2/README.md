# Second Opus run and adjudication (wnja issue #8 flags)

The 4,193 flagged senses were reviewed blind a second time by Claude Opus,
with a fresh shuffle and new batch composition (`key.tsv`, `batchNN*.tsv`).

| run 1 \ run 2 | OK | WRONG | UNSURE |
|---|---|---|---|
| OK | 1,585 | 72 | 91 |
| WRONG | 79 | 2,042 | 69 |
| UNSURE | 85 | 88 | 75 |

Identical verdicts: 88.3%; OK/WRONG flips: 151 (3.6%).  The 566 senses
where the runs differ (or were both UNSURE) were adjudicated by a third
Opus pass that saw both earlier verdicts and reasons
(`adjudicate*.tsv`).

`final.tsv` has the decision for every flagged sense:

| decided by | remove | keep | lower confidence |
|---|---|---|---|
| both runs | 2,042 | 1,585 | – |
| adjudication | 235 | 144 | 187 |
| **total** | **2,277** | **1,729** | **187** |
