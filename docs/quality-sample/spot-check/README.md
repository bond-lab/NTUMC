# Human spot check of the wnja 2.1, COW 1.1 and Wordnet Bahasa 1.4 reviews

A native-speaker check of a stratified sample of the decisions made by the
LLM reviews, as released in COW 1.1 and Wordnet Bahasa 1.4 (`../full-review/`)
and in wnja 2.1 (the issue #8 audit, `../wnja-opus2/`, and the JSemCor review
in the wnja repository).  Made by `scripts/spot_check.py make` (fixed seed); scored by
`scripts/spot_check.py score`.

**Send checkers only their `<lang>-sheet.tsv` and the instructions below.**
`key/` gives the model decision for each item and must stay hidden until
the sheet is returned.

| | cmn (Mandarin) | id (Indonesian) | zsm (Malay) | ja (Japanese) |
|---|---|---|---|---|
| Items | 220 | 166 | 181 | 200 |

The Japanese checker gets `ja-sheet.tsv` and `ja-instructions.md` (the
instructions in Japanese and English).

## Instructions for checkers

Each row is a word with one meaning, given by the English words and
definition (and, when there is one, a definition in your language).  The
items are in random order; some are right, some are wrong.  Please fill in
three columns (the file opens in LibreOffice or Excel as tab-separated
UTF-8; keep the file in that format):

* `meaning`: does the word have this meaning in your language?
  * `OK`: yes, this is a normal way to express this meaning (it may also
    have other meanings);
  * `WRONG`: no;
  * `UNSURE`: you cannot tell, or it is borderline.
* `form`: is the word itself well formed?  Leave it empty if it is fine,
  otherwise write
  * `malformed`: a typo, a phrase or explanation rather than a word, the
    wrong script (e.g. traditional characters for Mandarin), or stray
    spaces;
  * for Indonesian, `Malaysian only`: used in Malaysia but not in Indonesia;
  * for Malay, `Indonesian only`: used in Indonesia but not in Malaysia.
* `comment`: optional; a better word, or why you are unsure.

`other_words_in_synset` lists the other words given for the same meaning,
which may help; they are not being checked.  Judge each item on its own
and do not look anything up beyond what you would normally use (a
dictionary is fine).  Roughly 100 items an hour is a normal pace.

## Strata

`key/strata.tsv` gives the population and sample size of each stratum
(20 per stratum; 40 for unflagged senses, where errors are rarer; all
items when a stratum is smaller).

| Stratum | Decision | Supported if the checker says |
|---|---|---|
| `remove-wrong` | removed, both Opus runs said wrong | `WRONG` |
| `remove-wrong-adj` | removed, wrong by adjudication | `WRONG` |
| `remove-form` | removed for a form note | `form` not empty |
| `keep` | flagged by Haiku, kept (both runs said right) | `OK`, form fine |
| `keep-adj` | flagged, kept by adjudication | `OK`, form fine |
| `lower` | undecided, confidence 0.5 | (distribution reported) |
| `unflagged` | not flagged by Haiku, kept | `OK`, form fine |
| `rename` | malformed lemma, fixed form shown | `OK`, form fine |
| `rename-mechanical` | `form_fixes.py` rename, fixed form shown | `OK`, form fine |
| `rescue` | added from excluded sources (cmn) | `OK`, form fine |
| `move` | added from the other variety of Malay | `OK`, form fine |
| `jsemcor-add` | added from the JSemCor review (ja) | `OK`, form fine |
| `jsemcor-reject` | JSemCor candidate judged wrong, not added (ja) | `WRONG` |

For wnja the strata come from the reviews that changed it, not from a Haiku
triage: `remove-wrong(-adj)`, `keep(-adj)` and `lower` are the 4,193
senses flagged by the issue #8 audit; `unflagged` are wnja 2.1 senses
that neither the audit nor the JSemCor review touched; `rename-mechanical`
are the full-width and okurigana fixes.  The context (other words,
Japanese definition) is taken from wnja 2.1 and the English from
`omw-en:2.0`, for every stratum alike.

For renamed senses the sheet shows the new form, and the key also gives
the old form.  Items the checker leaves blank are not counted.

## Scoring

Put the returned sheets back here under the same names, then run

    .venv/bin/python scripts/spot_check.py score

which writes `key/score.tsv`: per language and stratum, the number of items
checked, the share supporting the decision and a 95% Wilson interval.
Multiplying by the stratum populations gives, for example, how many of the
removed senses were in fact right, and how many wrong senses remain among
the unflagged ones.
