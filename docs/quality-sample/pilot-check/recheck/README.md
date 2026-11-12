# Second opinion on the disputed pilot removals

Of the 50 pilot removals on the pilot-check sheet (`../`), the first
checker judged only 21 WRONG.  Some of their OKs look generous, so this
blind sheet asks a second checker about the 29 they did not judge WRONG
(24 OK, 5 UNSURE), mixed with 6 they did judge WRONG as a control, in
random order.  It is not the same checker, and they do not see the first
answers or the models' verdicts.

Made by `scripts/pilot_review.py recheck` (fixed seed).  **Send only
`ja-recheck-sheet.tsv` and the instructions below.**  `key/` has the first
checker's answers.  The returned sheet goes in `returned/` under the same
name.

## 日本語

日本語 WordNet の単語と意味の組を 35 項目確認していただきたいです。前回と同じ形式で、各行は日本語の単語と一つの意味（英語の単語と定義、日本語の定義）です。日本語の定義は機械翻訳なので、意味は英語で判断してください。

* `meaning`: その単語がこの意味を表す普通の言い方か。`OK`（他の意味があっても構いません）、`WRONG`、`UNSURE`。
* `form`: 単語の形に問題がなければ空欄。誤字、句や説明、複数の語の連なりなどであれば `malformed`。
* `comment`（任意）: より良い単語、迷った理由など。

`other_words_in_synset` は同じ意味に付けられた他の単語で、参考用です（確認の対象ではありません）。15〜20 分ほどの作業です。`key/` フォルダは見ないでください。

## English

Please check 35 pairs of a word and a meaning from the Japanese WordNet.
The format is the same as before: each row is a Japanese word with one
meaning (English words and definition, and a Japanese definition).  The
Japanese definition was machine translated, so judge the meaning by the
English.

* `meaning`: is the word a normal way to express this meaning?  `OK` (it
  may have other meanings), `WRONG` or `UNSURE`;
* `form`: empty if the word is fine, otherwise `malformed` (a typo, a
  phrase or explanation, several words run together, ...);
* `comment` (optional): a better word, or why you are unsure.

`other_words_in_synset` lists other words for the same meaning, for
reference; they are not being checked.  It should take 15–20 minutes.
Please do not look at `key/`.
