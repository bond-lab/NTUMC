"""
Japanese POS tag mappings for the NTUMC WordNet tagging system.

This module maps Japanese POS tags to WordNet categories.
"""
from typing import Dict, Set
from ntumc.config.language.base_mappings import POSMapper


class JapanesePOSMapper(POSMapper):
    """POS mapper for Japanese."""
    
    def pos_to_wn(self, pos: str, lemma: str = '') -> str:
        """
        Map a Japanese POS tag to a WordNet category.
        
        Args:
            pos: The POS tag to map
            lemma: Optional lemma for context-dependent mapping
            
        Returns:
            str: WordNet category ('n', 'v', 'a', 'r', 'x', or 'u')
        """
        if pos in ['名詞-形容動詞語幹', "形容詞-自立", "連体詞"] \
                and not lemma in ["この", "その", "あの"]:
            return 'a'
        elif pos in ["名詞-サ変接続",  "名詞-ナイ形容詞語幹", 
                    "名詞-一般", "名詞-副詞可能",  
                    "名詞-接尾-一般", "名詞-形容動詞語幹", 
                    "名詞-数",  "記号-アルファベット"]:
            return 'n'
        elif pos == "動詞-自立":
            return 'v'
        elif pos in ["副詞-一般", "副詞-助詞類接続"]:
            return 'r'
        else:
            return 'x'
