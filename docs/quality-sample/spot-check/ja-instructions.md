# 日本語 WordNet の確認作業 / Checking Japanese WordNet senses

## 日本語

日本語 WordNet 2.1 では、大規模言語モデル（LLM）による確認の結果、誤りと判断された語義が削除され、新しい語義が追加されました。モデルの判断がどの程度正しいかを、日本語母語話者の目で確かめていただくのがこの作業の目的です。

`ja-sheet.tsv` には 290 項目あります（二人目の確認者には、その一部 50 項目の `ja-overlap-sheet.tsv` をお願いします）。各項目は、一つの意味（英語の単語と英語の定義、日本語の定義）と一つの日本語の単語の組です。正しいものも誤っているものも、ランダムな順番で並んでいます。各項目について、次の三つの列を記入してください。

* `meaning`（意味）: その単語がこの意味を表す普通の言い方かどうか。
  * `OK`: はい（他の意味があっても構いません）
  * `WRONG`: いいえ
  * `UNSURE`: 判断できない、または微妙
* `form`（形）: 単語の形そのものに問題がなければ空欄のままにしてください。問題があれば `malformed` と書いてください（誤字、単語ではなく句や説明、全角の英数字、送り仮名がカタカナになっているなど）。
* `comment`（任意）: より良い単語や、迷った理由など。

`other_words_in_synset` は同じ意味の他の単語で、参考にしてください（これらは確認の対象ではありません）。各項目はそれぞれ独立に判断してください。普段使うもの（辞書など）は使って構いませんが、それ以上の調査は不要です。1 時間に 100 項目程度、全体で 3 時間ほど（50 項目なら 30 分ほど）が目安です。何回かに分けても構いません。

ファイルはタブ区切りの UTF-8 です。LibreOffice Calc や Google スプレッドシートではそのまま開けます。Excel の場合は「データ」→「テキストまたは CSV から」で UTF-8 を選んでください（文字化けを防ぐため）。記入したら同じ形式で返送してください。

お願い：この確認はモデルの答えを見ずに行うことが大切です。GitHub の NTU-MC リポジトリにある `docs/quality-sample/spot-check/key/` フォルダ（モデルの答え）は見ないでください。

## English

Japanese WordNet 2.1 removed senses that large language models judged wrong and added new ones; this check measures how often the models were right.

`ja-sheet.tsv` has 290 items (a second checker gets `ja-overlap-sheet.tsv`, 50 of them). Each is a Japanese word with one meaning, given by English words, an English definition and a Japanese definition. Some are right and some are wrong, in random order. Please fill in

* `meaning`: `OK` (a normal way to say this; it may have other meanings), `WRONG`, or `UNSURE`;
* `form`: empty if the word itself is fine, otherwise `malformed` (a typo, a phrase or explanation rather than a word, full-width letters or digits, katakana okurigana, ...);
* `comment` (optional): a better word, or why you are unsure.

`other_words_in_synset` lists other words for the same meaning, which may help; they are not being checked. Judge each item on its own, using only what you would normally use (a dictionary is fine). About 100 items an hour, so about 3 hours (half an hour for 50 items); it can be done in several sittings.

The file is tab-separated UTF-8: it opens in LibreOffice Calc or Google Sheets; in Excel use Data → From Text/CSV and choose UTF-8. Please send it back in the same format, and do not look at `docs/quality-sample/spot-check/key/` in the NTU-MC repository, which has the models' answers.
