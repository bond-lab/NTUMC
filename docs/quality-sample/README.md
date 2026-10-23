# Sense quality check of the 2026-10 releases

A first estimate of how many senses in the basic vocabulary of wnja 2.0,
COW 1.0 and Wordnet Bahasa 1.3 are wrong (2026-10-23).

## Method

* **Sampling frame:** senses in synsets that the TUFS Basic Vocabulary
  wordnet for the same language also has (see `../tufs-comparison.md`):
  4,283 (ja), 1,882 (cmn), 2,175 (id) and 1,710 (zsm) senses.
* **Sample:** 100 senses per language, drawn at random with seed 20261023
  (`<lang>-sample.tsv`, with the English words and definition from
  `omw-en:2.0`).
* **Review:** one LLM reviewer (Claude Sonnet) per language judged each
  word as OK, WRONG (different meaning), FORM (right meaning, malformed
  lemma or the other variety of Malay) or UNSURE (`<lang>-review.tsv`).
* **Spot check:** 15 of the WRONG calls checked by hand against the
  English definitions; 12 confirmed.

## Results

| | wnja (ja) | COW (cmn) | wnb-id | wnb-zsm |
|---|---|---|---|---|
| OK | 84 | 90 | 77 | 76 |
| WRONG | 8 | 4 | 9 | 12 |
| FORM | 1 | 3 | 4 | 5 |
| UNSURE | 7 | 3 | 10 | 7 |

With 100 senses, each figure is about ±6 points (95% interval).

## What the errors look like

* **Translation through an ambiguous English word**, the main pattern:
  back → 後押し 'pushing from behind'; teach/learn → *mempelajari*
  'study'; answer/resolve → *membalas* 'reply'; turn → *berkisar*
  'revolve'; thick → 深厚 'profound', 朦々たる 'hazy'; journal → *diari*.
* **Malay and Indonesian mixed up:** Malaysian forms in the Indonesian
  wordnet (*pensel*, *soalan*, *tempoh*, *berlepas*) and the reverse
  (*merekam*, *beristirahat*, *ketemu*).
* **Malformed lemmas in COW:** an annotation (脱（衣帽等）), a phrase
  (沾上泥污), a full-width digit (２月).

## Caveats

* The reviewer is an LLM.  At least three Malay WRONG calls are doubtful
  (*silam* also means 'dark', *bekas* 'second-hand' fits 'not new',
  *ribut* can mean 'busy, in a fuss').  For Japanese it was strict with
  historical words (勝手方, 御錠口); all eight questioned wnja senses are
  marked `hand` in the NICT 1.1 data.
* The sample is basic vocabulary, where TUFS also has the synset; error
  rates elsewhere may differ.
