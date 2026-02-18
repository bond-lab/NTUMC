"""
English POS tag mappings for the NTUMC WordNet tagging system.

This module maps English POS tags to WordNet categories.
"""
from typing import Dict
from ntumc.config.language.base_mappings import POSMapper


class EnglishPOSMapper(POSMapper):
    """POS mapper for English."""
    
    def pos_to_wn(self, pos: str, lemma: str = '') -> str:
        """
        Map an English POS tag to a WordNet category.
        
        Args:
            pos: The POS tag to map
            lemma: Optional lemma for context-dependent mapping
            
        Returns:
            str: WordNet category ('n', 'v', 'a', 'r', 'x', or 'u')
        """
        if  pos == 'VAX':  #local tag for auxiliaries
            return 'x'
        elif pos in ['NN', 'NNS', 'NNP', 'NNPS', 
                     'CD', 'WP', 'PRP']: 
            # include proper nouns and pronouns
            return 'n'
        elif pos.startswith('V'):
            return('v')
        elif pos.startswith('J') or \
             pos in ['WDT',  'WP$', 'PRP$', 'PDT', 'PRP'] or \
             (pos=='DT' and not lemma in ['a', 'an', 'the']):
            ### adjectives, some pronouns, most determiners
            return('a')
        elif pos.startswith('RB') or pos == 'WRB':
            return('r')
        else:
            return 'x'
