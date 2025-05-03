Tag a span in the specified ntumc databse

something like

tag-llm.py from:to ntumc.db

calling it with --dry-run just prints the selected tags to standard out

calling it with -m or --model allows you to specify the model (use the same names as ollama, defualt to qwen3:8b

Tagging is done using a LLM, usiing a prompt something like:

```
110372.8 Which meaning of the word _pearl_ is expressed in the following context: 

A sea captain or something.
They said he’d been out looking for pearls.”
Mister Golombek looked at Mister Valenta.


The meanings are as follows: 
{'13901585-n': '{drop, bead, pearl} a shape that is spherical and small',
'13372403-n': {pearl} a smooth lustrous round structure inside the shell of a clam or oyster; much valued as a jewel',
'01383800-v': {pearl} 'gather pearls, from oysters in the ocean',
'80000204-n': {pearl}' 'a person or thing that is beautiful, brilliant or valuable, like a pearl',
'04961331-n':{ivory, pearl, bone, off-white, pearl-white} a shade of white the color of bleached bones'}

Return only the key of the most relevant meaning.
```
The first part is the text, and the second part are the meanings.

However, we use NTUMC for the corpus, so let's show one sentence
before and after for the context.

The meanings are taken from the wordnet.

Currently wordnet_db.py does not have a method to return the definitions, so we would need to add that.


We also have 9 possible other tags:
```
'per':'name of a person not in wordnet',
# e.g. Irene Adfer
'org':'name of an organization in wordnet',
# IBM
'dat':'date/time that is not in wordnet',
# 2pm
'loc':'name of a place not in wordnet',
# Olomouc
'oth':'other name not in wordnet',
# Thinkpad
'year':'name of a year not in wordnet'
# 1967
'e':'the word was not tokenized or lemmatized correctly',
# 'I saw three _does_' lemmatized as _do_
'w':'wordnet does not have the correct sense',
# 'I program in _python_' meaning "the computer language"
'x':'this is a closed class word (preposition, dummy it/there, relative pronoun passive or progressive be/have) or an element of a larger multiword expression'
# 'Kim scored a _hat_ trick' this should be part of _at trick_
```
Use ollama python to access the library.


Given the context:

> A sea captain or something. They said he’d been out looking for pearls. Mister Golombek looked at Mister Valenta.

Prompt:
```
Identify the correct tag for _Golombek_from these options:

{'13901585-n': '{drop, bead, pearl} a shape that is spherical and small', '13372403-n': '{pearl} a smooth lustrous round structure inside the shell of a clam or oyster; much valued as a jewel', '01383800-v': '{pearl} gather pearls, from oysters in the ocean', '80000204-n': '{pearl} a person or thing that is beautiful, brilliant or valuable, like a pearl', '04961331-n': '{ivory, pearl, bone, off-white, pearl-white} a shade of white the color of bleached bones', 'per': 'name of a person not in wordnet', 'org': 'name of an organization not in wordnet', 'dat': 'date/time that is not in wordnet', 'loc': 'name of a place not in wordnet', 'oth': 'other name not in wordnet', 'year': 'name of a year not in wordnet', 'e': 'the word was not tokenized or lemmatized correctly', 'w': 'wordnet does not have the correct sense', 'x': 'this is a closed class word or part of a multiword expression'}

Return only the tag's key.
```
