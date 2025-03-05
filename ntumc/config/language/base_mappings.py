"""
Base interface for language-specific POS mappings.

This module defines the interface for mapping language-specific POS tags
to WordNet categories (n, v, a, r, x, u).
"""
from typing import Callable, Optional, Dict, Any
from abc import ABC, abstractmethod


class POSMapper(ABC):
    """Abstract base class for POS mappers."""
    
    @abstractmethod
    def pos_to_wn(self, pos: str, lemma: str = '') -> str:
        """
        Map a language-specific POS tag to a WordNet category.
        
        Args:
            pos: The POS tag to map
            lemma: Optional lemma for context-dependent mapping
            
        Returns:
            str: WordNet category ('n', 'v', 'a', 'r', 'x', or 'u')
                n: noun
                v: verb
                a: adjective
                r: adverb
                x: not a content word
                u: unknown (undefined)
        """
        pass


def get_pos_mapper(lang_code: str) -> POSMapper:
    """
    Get the POS mapper for a specific language.
    
    Args:
        lang_code: Language code in ISO 639-3 format
        
    Returns:
        POSMapper: The POS mapper for the specified language
        
    Raises:
        ValueError: If the language is not supported
    """
    from ntumc.config.language.eng_mappings import EnglishPOSMapper
    from ntumc.config.language.ces_mappings import CzechPOSMapper
    from ntumc.config.language.jap_mappings import JapanesePOSMapper
    from ntumc.config.language.zsm_mappings import ChinesePOSMapper
    from ntumc.config.language.vie_mappings import VietnamesePOSMapper
    
    mappers = {
        "eng": EnglishPOSMapper(),
        "ces": CzechPOSMapper(),
        "jap": JapanesePOSMapper(),
        "zsm": ChinesePOSMapper(),
        "vie": VietnamesePOSMapper(),
    }
    
    if lang_code not in mappers:
        raise ValueError(f"No POS mapper available for language: {lang_code}")
    
    return mappers[lang_code]


def pos_to_wn(pos: str, lang_code: str, lemma: str = '') -> str:
    """
    Map a language-specific POS tag to a WordNet category.
    
    This is a convenience function that uses the appropriate POS mapper
    for the specified language.
    
    Args:
        pos: The POS tag to map
        lang_code: Language code in ISO 639-3 format
        lemma: Optional lemma for context-dependent mapping
        
    Returns:
        str: WordNet category ('n', 'v', 'a', 'r', 'x', or 'u')
    """
    mapper = get_pos_mapper(lang_code)
    return mapper.pos_to_wn(pos, lemma)
