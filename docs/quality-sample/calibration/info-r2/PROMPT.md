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

Write a TSV with the header `id	verdict	reason` (verdict OK, WRONG or UNSURE; reason in a few English words) and one row for every input row.
