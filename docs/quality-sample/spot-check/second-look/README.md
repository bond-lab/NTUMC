# Second look at 21 disputed items

On these items the first checker's answer differs from that of all four
model prompts in the calibration (`../../calibration/`).  This is not a
blind check: each row shows the checkers' answers and the model's, with
its reason, and asks for a final answer.  The final answers replace the
first checker's in the development labels, and decide four wnja changes
made on the first checker's word (出発 restored; さし通す, トランス系 and
スリット removed).  Returned sheets go in `../returned/` as
`ja-second-look.tsv`.

## 日本語

先日は確認作業をありがとうございました。この 21 項目では、皆さんの答えと言語モデル（4 種類の指示のすべて）の答えが分かれました。どちらが正しいか、もう一度見ていただけますか。今回はブラインドではありません。各行に、一人目の答え（`first_answer`, `first_comment`）、二人目の答え（あれば `second_answer`, `second_comment`）、モデルの答えと理由（`model_answer`, `model_reason`）、JMdict の英語の訳（`jmdict`）を載せています。

`answer` に最終的な答え（`OK`, `WRONG`, `UNSURE`）を、`comment` に理由などを書いてください。前の答えが正しいと思えば、そのままで構いません。基準は前回と同じで、その単語がこの意味（英語の定義）を表す普通の言い方かどうかです。10〜15 分ほどの作業です。

## English

Thank you again for the check.  On these 21 items your answers and the
language models' (all four prompts) differ; could you look at them once
more?  This time it is not blind: each row shows the first checker's
answer (`first_answer`, `first_comment`), the second checker's if there is
one (`second_answer`, `second_comment`), the model's answer and reason
(`model_answer`, `model_reason`) and the word's English glosses in JMdict
(`jmdict`).

Write your final answer in `answer` (`OK`, `WRONG` or `UNSURE`) and any
reason in `comment`; if the earlier answer was right, just repeat it.  The
question is the same as before: is the word a normal way to express this
meaning (the English definition)?  It should take 10–15 minutes.
