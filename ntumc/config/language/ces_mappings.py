"""
Czech POS tag mappings for the NTUMC WordNet tagging system.

This module maps Czech POS tags to WordNet categories.
"""
from typing import Dict, Set
from ntumc.config.language.base_mappings import POSMapper


class CzechPOSMapper(POSMapper):
    """POS mapper for Czech."""
    
    def __init__(self):
        """Initialize the Czech POS mapper with tag mappings."""
        self.noun_tags = {'NOUN', 'PRON', 'PROPN', 'NUM'}
        self.verb_tags = {'VERB', 'AUX'}
        self.adj_tags = {'DET', 'ADJ'}
        self.adv_tags = {'ADV', 'INTJ', 'PART'}
    
    def pos_to_wn(self, pos: str, lemma: str = '') -> str:
        """
        Map a Czech POS tag to a WordNet category.
        
        Args:
            pos: The POS tag to map (UPOS format)
            lemma: Optional lemma for context-dependent mapping
            
        Returns:
            str: WordNet category ('n', 'v', 'a', 'r', 'x', or 'u')
        """
        if pos in self.noun_tags:
            return 'n'
        elif pos in self.verb_tags:
            return 'v'
        elif pos in self.adj_tags:
            return 'a'
        elif pos in self.adv_tags:
            return 'r'
        else:
            return 'x'
