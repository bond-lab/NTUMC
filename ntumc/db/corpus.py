##
## This is an interface to the corpus, 
##

# It should provide a doc, which gives:
#   * docid, doc, title, subtitle, and corpusID
#   * sentences
#   * words
#   * concepts

#   Sentences have
#   * sid
#   * text
#   * stype (with optional comment) from stype table
#   * comment

#   Words have
#   * sid, wid
#   * word
#   * POS
#   * lemma
#   * comment

#   Concepts have
#    * sid, cid
#    * wids (from cwl)
#    * lemma
#    * tag
#    * comment
#    * sentiment (from sentiment)

#  These should be available as a class
#  There should be a method to dump as json or yaml
 
