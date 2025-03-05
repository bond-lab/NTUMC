"""
Chinese POS tag mappings for the NTUMC WordNet tagging system.

This module maps Chinese POS tags to WordNet categories.
"""
from typing import Dict, Set
from ntumc.config.language.base_mappings import POSMapper


class ChinesePOSMapper(POSMapper):
    """POS mapper for Mandarin Chinese."""
    
    def __init__(self):
        """Initialize the Chinese POS mapper with tag mappings."""
        self.noun_tags = set("NN NN2 CD DT PN PN2 LC M M2 NR NT".split())
        self.verb_tags = set("VV VV2 VC VE".split())
        self.adj_tags = set("JJ JJ2 OD VA VA2".split())
        self.adv_tags = set("AD AD2 ETC ON".split())
    
    def pos_to_wn(self, pos: str, lemma: str = '') -> str:
        """
        Map a Chinese POS tag to a WordNet category.
        
        Args:
            pos: The POS tag to map
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
