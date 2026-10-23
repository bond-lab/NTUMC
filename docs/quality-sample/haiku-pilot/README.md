# Haiku triage pilot (wnja)

Can Claude Haiku serve as a cheap first filter, with flagged senses sent
on to the double Opus review?  300 wnja senses, shuffled blind
(`key.tsv`): 100 judged WRONG by both Opus runs, 100 judged OK by both
(hard cases flagged in issue #8), 100 random unflagged.  Haiku was asked
to mark each OK or SUSPECT, flagging when in doubt.

| group | flagged SUSPECT |
|---|---|
| WRONG (both Opus runs) | 94 / 100 |
| OK (both Opus runs) | 29 / 100 |
| random unflagged | 13 / 100 |

Recall on known errors about 94%, background flag rate about 13%.
Calibrated on Japanese only.
