Tag a span in the specified ntumc databse

something like

tag-llm.py from:to ntumc.db

calling it with --dry-run just prints the selected tags to standard out

calling it with -m or --model allows you to specify the model (use the same names as ollama, default to qwen3:8b

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
'x':'this is a closed class word (preposition, dummy it/there, relative pronoun passive or progressive be/have) or an element of a larger multiword expression or an inappropriate multiword expression'
# 'Kim scored a _hat_ trick' this should be part of _hat trick_
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


~~Test and document sentiment~~

~~Test and document adding examples
Add examples to the special tags!~~

have options to not include examples or senses

Write to the DB!

Maybe add a very short note about which POS match wordnet, and list some bad POS classes.
e.g. determiner and quantifier are 'a', PP can be 'r', nominals can be 'n', VP can be 'n'.

~~Add that the word is lemmatized.~~

------------------------------------------------------------------------


Add context as shown in claude:

def generate_and_extract(
    prompt: str, 
    model: str = 'llama3', 
    context: Optional[List[int]] = None
) -> Tuple[Optional[str], str, Optional[List[int]]]:
    """
    Generate a response with optional context maintenance and thinking extraction.
    
    Args:
        prompt (str): The input prompt for the model.
        model (str, optional): The Ollama model to use. Defaults to 'llama3'.
        context (Optional[List[int]], optional): Previous conversation context. Defaults to None.
    
    Returns:
        Tuple containing:
        - thinking (Optional[str]): Extracted thinking process, if present
        - cleaned_response (str): Response with thinking process removed
        - new_context (Optional[List[int]]): Updated conversation context
    """
    # Prepare generation parameters
    generate_kwargs = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    
    # Add context if provided
    if context is not None:
        generate_kwargs["context"] = context
    
    # Generate response
    try:
        result = ollama.generate(**generate_kwargs)
        response = result['response']
        
        # Extract thinking process
        think_match = re.search(r'<think>(.*?)</think>', response, re.DOTALL)
        
        if think_match:
            thinking = think_match.group(1).strip()
            # Remove the thinking part from the main response
            cleaned_response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
        else:
            thinking = None
            cleaned_response = response.strip()
        
        # Return thinking, cleaned response, and new context
        return thinking, cleaned_response, result.get('context')
    
    except Exception as e:
        print(f"Error in generate_and_extract: {e}")
        return None, "", None

# Example usage demonstration
def main():
    # First query without context
    first_prompt = "Explain quantum physics in simple terms. Use <think> tags for your reasoning."
    first_thinking, first_response, first_context = generate_and_extract(first_prompt)
    
    print("First Query:")
    
========================================================================


time python ntumc/taggers/tag-llm.py 110499:110526 eng.db /home/bond/work/Newt/2024w/wn-ntumc.db --dry-run -m gemma3:12b > poi-gemma3:12b

real	4m15.831s
user	0m0.502s
sys	0m0.071s

(/ (* 4.25 60) 200.0) 1.275  seconds /concept

time python ntumc/taggers/tag-llm.py 110499:110526 eng.db /home/bond/work/Newt/2024w/wn-ntumc.db --dry-run -m qwen3:14b > poi-qwen3:14b

real	81m42.027s
user	0m0.500s
sys	0m0.101s

This is for 200 concepts.

(/ (* 81 60) 200.0) 24.3  24 seconds /concept

For the whole class there are 200 * 40 concepts:

(/ (* 200 82) (* 24 60.0)) 11.38888888888889  12 days full time!


time python ntumc/taggers/tag-llm.py 110499:110526 eng.db /home/bond/work/Newt/2024w/wn-ntumc.db --dry-run -m gemma3:27b --verbose > poi-gemma3\:27b-senti 2>&1

real	16m48.843s
user	0m0.528s
sys	0m0.057s

time python ntumc/taggers/tag-llm.py 110499:110526 eng.db /home/bond/work/Newt/2024w/wn-ntumc.db --dry-run -m deepseek-r1:14b --verbose > deepseek-r1\:14b 2>&1
real	66m5.903s
user	0m0.385s
sys	0m0.043s

COMMENT: very bad about giving the answer as a plain string


time python ntumc/taggers/tag-llm.py 110499:110526 engL.db /home/bond/work/Newt/2024w/wn-ntumc.db --verbose -m qwen3:14b > poi-qwen3\:14b-ex  2>&1

real	132m18.296s
user	0m0.651s
sys	0m0.150s
