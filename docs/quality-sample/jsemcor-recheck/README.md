# Recheck of the rejected JSemCor senses

The Japanese SemCor translators used a Japanese word for an English word
tagged with a synset; wnja 2.1 added the 1,347 such pairs that a blind
double Opus review accepted (wnja issue #11).  The native-speaker spot
check (`../spot-check/`) found all 20 sampled additions right but only 3
of 20 sampled rejections right: the reviewers wanted an exact equivalent,
and rejected near-synonyms that are normal translations (治療 *cure*, 読者
*reader*, 伴う *follow*).  So the remaining 1,182 rejections go to a native
checker.

Made by `scripts/jsemcor_recheck.py make` (fixed seed).  67 rejected pairs
whose synset has no wnja synset are left out; the 20 already in the spot
check are not repeated.

**Send checkers only `ja-jsemcor-sheet.tsv` (or the 50-item
`ja-jsemcor-overlap-sheet.tsv`, for a second checker) and the
instructions below.**  `key/` has the models' verdicts.  Returned sheets go
in `returned/` under the same names.

Pairs judged OK with no form note are then to be added to wnja
(`corrections/senses.tsv`, `add`, with this check as the source).

## 日本語

日本語 SemCor の翻訳者は、ある意味（synset）の英単語を訳すときに、ある日本語の単語を使いました。この表は、そうした組のうち、言語モデルが「この意味には合わない」と判断して日本語 WordNet に追加しなかったものです。先日の確認では、その多くが実際には正しい訳でした。

`ja-jsemcor-sheet.tsv` には 1,182 項目あります（二人目の確認者は `ja-jsemcor-overlap-sheet.tsv` の 50 項目）。各項目について、前回と同じ三つの列を記入してください。

* `meaning`: その単語がこの意味を表す普通の言い方か。`OK`（他の意味があっても構いません）、`WRONG`、`UNSURE`。
* `form`: 単語の形に問題がなければ空欄。誤字、句や説明、複数の語の連なりなどであれば `malformed`。
* `comment`（任意）: より良い単語、迷った理由など。

`example_en` と `example_ja` は、翻訳者がこの単語を使った文の対です。参考にしてください。ただし、文の中では適切な訳でも、単語がその意味を表すとは限りません（意訳など）。判断するのは、英語の定義の意味をその単語で普通に表せるかどうかです。

1 時間に 100 項目程度、全体で 12 時間ほどが目安です。何回かに分けても構いません。モデルの答え（`key/` フォルダ）は見ないでください。

## English

The JSemCor translators used a Japanese word for an English word with a
given meaning (synset).  These are the pairs that language models judged
not to fit the meaning, so they were not added to the Japanese WordNet;
the earlier check found most of them were in fact right.

`ja-jsemcor-sheet.tsv` has 1,182 items (a second checker gets the 50 in
`ja-jsemcor-overlap-sheet.tsv`).  Fill in the same three columns as before:

* `meaning`: is the word a normal way to express this meaning?  `OK` (it
  may have other meanings), `WRONG` or `UNSURE`;
* `form`: empty if the word is fine, otherwise `malformed` (a typo, a
  phrase or explanation, several words run together, ...);
* `comment` (optional): a better word, or why you are unsure.

`example_en` and `example_ja` are the sentence pair in which the
translator used the word.  A word can be a good translation in context
without having the meaning (a free translation), so judge whether the
word normally expresses the meaning of the English definition.

About 100 items an hour, so about 12 hours; it can be done in several
sittings.  Please do not look at `key/`, which has the models' answers.
