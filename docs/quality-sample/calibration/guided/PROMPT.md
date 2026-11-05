You are checking senses in the Japanese WordNet, as a native speaker
would.  Each row is a Japanese word with one meaning, given by the English
words and definition (and a definition in Japanese).  For each row decide
whether the word has this meaning in Japanese:
  OK: yes, this is a normal way to express this meaning (it may also have
      other meanings);
  WRONG: no;
  UNSURE: you cannot tell, or it is borderline.
`other_words_in_synset` lists other words given for the same meaning, which may
help; they are not being checked.  Judge each item on its own.
Extra columns may help: `readings` (kana), `jmdict` (the word's English glosses
in the JMdict dictionary, with tags such as archaic or rare in brackets, senses
separated by |; empty if the word is not in JMdict), `other_senses_of_word`
(English words of the word's other synsets in the Japanese WordNet),
`english_hypernyms` and `english_example` (for the synset).  The Japanese
definition was machine translated and may be wrong; judge the meaning given by
the English.
Guidance:
* Judge whether the word can express the meaning, not whether it is the best
  or the only word: a near-synonym or a word translators would normally use
  for it is OK, even if its range is a little wider or narrower.
* A rare, old, literary or technical word is OK if a dictionary gives this
  meaning; do not mark a word WRONG only because it is unfamiliar.
* Mark WRONG when the word does not have this meaning: typically it was
  reached through another sense of an ambiguous English word (a slot in a
  river is not a 銀行), names a related but different thing (an
  institution for an act, a person for a place), or is a different part of
  speech or a fixed phrase that cannot stand for the meaning.
* Use UNSURE sparingly, only when the evidence really is balanced.

Write a TSV with the header `id	verdict	reason` (verdict OK, WRONG or UNSURE; reason in a few English words) and one row for every input row.
