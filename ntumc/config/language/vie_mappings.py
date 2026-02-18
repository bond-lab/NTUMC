"""
Vietnamese POS tag mappings for the NTUMC WordNet tagging system.

This module maps Vietnamese POS tags to WordNet categories.
"""
from typing import Dict, Set
from ntumc.config.language.base_mappings import POSMapper


class VietnamesePOSMapper(POSMapper):
    """POS mapper for Vietnamese."""
    
    def __init__(self):
        """Initialize the Vietnamese POS mapper with tag mappings."""
        self.noun_tags = set("N Np Nc Nu Ny B".split())
        self.verb_tags = set("V".split())
        self.adj_tags = set("A".split())
        self.adv_tags = set("L R".split())
    
    def pos_to_wn(self, pos: str, lemma: str = '') -> str:
        """
        Map a Vietnamese POS tag to a WordNet category.
        
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
