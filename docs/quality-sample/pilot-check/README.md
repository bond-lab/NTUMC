# Native check of the pilot review decisions

The pilot (`../pilot-review/`) had two blind model runs decide on 5,000
wnja senses that no earlier audit had flagged: keep, remove, lower to 0.8,
or lower to 0.5 and queue for a person.  This sheet is a blind, stratified
sample of those decisions (50 removed, 30 queued, 30 lowered, 30 kept, in
random order) to measure how often each action is right.  These items are
not development data: keep them out of prompts.

Made by `scripts/pilot_review.py sheet` (fixed seed); scored by
`scripts/pilot_review.py check`, which writes `key/score.tsv`.

**Send checkers only `ja-pilot-sheet.tsv` and the instructions below.**
`key/` has the decisions and the models' verdicts.  The returned sheet
goes in `returned/` under the same name.

## 日本語

日本語 WordNet の単語と意味の組を 140 項目確認していただきたいです。前回の確認と同じ形式で、各行は日本語の単語と一つの意味（英語の単語と定義、日本語の定義）です。日本語の定義は機械翻訳なので、意味は英語で判断してください。

* `meaning`: その単語がこの意味を表す普通の言い方か。`OK`（他の意味があっても構いません）、`WRONG`、`UNSURE`。
* `form`: 単語の形に問題がなければ空欄。誤字、句や説明、複数の語の連なりなどであれば `malformed`。
* `comment`（任意）: より良い単語、迷った理由など。

`other_words_in_synset` は同じ意味に付けられた他の単語で、参考用です（確認の対象ではありません）。1 時間半ほどの作業です。`key/` フォルダは見ないでください。

## English

Please check 140 pairs of a word and a meaning from the Japanese WordNet.
The format is the same as the earlier check: each row is a Japanese word
with one meaning (English words and definition, and a Japanese definition).
The Japanese definition was machine translated, so judge the meaning by
the English.

* `meaning`: is the word a normal way to express this meaning?  `OK` (it
  may have other meanings), `WRONG` or `UNSURE`;
* `form`: empty if the word is fine, otherwise `malformed` (a typo, a
  phrase or explanation, several words run together, ...);
* `comment` (optional): a better word, or why you are unsure.

`other_words_in_synset` lists other words for the same meaning, for
reference; they are not being checked.  It should take about an hour and
a half.  Please do not look at `key/`.

## Returned (2026-11-12)

`returned/ja-pilot-sheet.tsv`, all 140 items; `key/score.tsv`:

| decision | OK | WRONG | UNSURE | WRONG of definite (95% interval) |
|---|---:|---:|---:|---|
| remove (both runs WRONG) | 24 | 21 | 5 | 0.47 (0.33-0.61) |
| queue for a person | 21 | 9 | 0 | 0.30 (0.17-0.48) |
| lower to 0.8 | 24 | 5 | 1 | 0.17 (0.08-0.35) |
| keep (both runs OK) | 29 | 0 | 1 | 0.00 (0.00-0.12) |

The review is reliable when it says OK and unreliable when it says WRONG:
only about half its removals were judged wrong, against 44 of 48 for the
issue #8 removals in the spot check.  Those had first been flagged by the
triage, so errors were common among them; among never-flagged senses
errors are rare (about 7%), and the same false-alarm rate gives about as many
good senses as bad among the removals.  The Codex filter helps a
little: of the removals gpt-6.1-sol also called WRONG, 20 were judged
WRONG and 16 OK.

Some of the checker's OKs look generous (郭大, a miswriting of 拡大, not
marked malformed; 食う *drink*; 切支丹 *Jesuitism*; 上天 *die*), and the
checker used `form` only once, so part of the gap may be the checker; but
many are reasonable broader uses that the models read too narrowly (守る
*continue*, 小っちゃい *lowly*, 不安定 *uncertainty*), as with the JSemCor
rejections.  These items are test data: keep them out of prompts.
