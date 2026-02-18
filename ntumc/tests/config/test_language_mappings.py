"""
Unit tests for language-specific POS mappings.

This module tests the mapping of language-specific POS tags to WordNet categories.
"""
import unittest
from ntumc.config.language.base_mappings import pos_to_wn, get_pos_mapper
from ntumc.config.language.eng_mappings import EnglishPOSMapper
from ntumc.config.language.ces_mappings import CzechPOSMapper
from ntumc.config.language.jap_mappings import JapanesePOSMapper
from ntumc.config.language.zsm_mappings import ChinesePOSMapper
from ntumc.config.language.vie_mappings import VietnamesePOSMapper


class TestEnglishMappings(unittest.TestCase):
    """Test English POS mappings."""
    
    def setUp(self):
        """Set up the test case."""
        self.mapper = EnglishPOSMapper()
    
    def test_common_pos_tags(self):
        """Test mapping of common English POS tags."""
        self.assertEqual(self.mapper.pos_to_wn('NN'), 'n')
        self.assertEqual(self.mapper.pos_to_wn('VB'), 'v')
        self.assertEqual(self.mapper.pos_to_wn('JJ'), 'a')
        self.assertEqual(self.mapper.pos_to_wn('RB'), 'r')
    
    def test_uncommon_pos_tags(self):
        """Test mapping of uncommon English POS tags."""
        self.assertEqual(self.mapper.pos_to_wn('CC'), 'x')
        self.assertEqual(self.mapper.pos_to_wn('IN'), 'x')
        self.assertEqual(self.mapper.pos_to_wn('DT'), 'a')
        self.assertEqual(self.mapper.pos_to_wn('DT',
                                               lemma='the'), 'x')
    
    def test_convenience_function(self):
        """Test the convenience function for mapping."""
        self.assertEqual(pos_to_wn('NN', 'eng'), 'n')
        self.assertEqual(pos_to_wn('VB', 'eng'), 'v')


class TestCzechMappings(unittest.TestCase):
    """Test Czech POS mappings."""
    
    def setUp(self):
        """Set up the test case."""
        self.mapper = CzechPOSMapper()
    
    def test_noun_tags(self):
        """Test mapping of Czech noun tags."""
        self.assertEqual(self.mapper.pos_to_wn('NOUN'), 'n')
        self.assertEqual(self.mapper.pos_to_wn('PRON'), 'n')
        self.assertEqual(self.mapper.pos_to_wn('PROPN'), 'n')
        self.assertEqual(self.mapper.pos_to_wn('NUM'), 'n')
    
    def test_verb_tags(self):
        """Test mapping of Czech verb tags."""
        self.assertEqual(self.mapper.pos_to_wn('VERB'), 'v')
        self.assertEqual(self.mapper.pos_to_wn('AUX'), 'v')
    
    def test_adj_tags(self):
        """Test mapping of Czech adjective tags."""
        self.assertEqual(self.mapper.pos_to_wn('ADJ'), 'a')
        self.assertEqual(self.mapper.pos_to_wn('DET'), 'a')
    
    def test_adv_tags(self):
        """Test mapping of Czech adverb tags."""
        self.assertEqual(self.mapper.pos_to_wn('ADV'), 'r')
        self.assertEqual(self.mapper.pos_to_wn('INTJ'), 'r')
        self.assertEqual(self.mapper.pos_to_wn('PART'), 'r')
    
    def test_other_tags(self):
        """Test mapping of other Czech tags."""
        self.assertEqual(self.mapper.pos_to_wn('CCONJ'), 'x')
        self.assertEqual(self.mapper.pos_to_wn('ADP'), 'x')
    
    def test_convenience_function(self):
        """Test the convenience function for mapping."""
        self.assertEqual(pos_to_wn('NOUN', 'ces'), 'n')
        self.assertEqual(pos_to_wn('VERB', 'ces'), 'v')


class TestJapaneseMappings(unittest.TestCase):
    """Test Japanese POS mappings."""
    
    def setUp(self):
        """Set up the test case."""
        self.mapper = JapanesePOSMapper()
    
    def test_noun_tags(self):
        """Test mapping of Japanese noun tags."""
        self.assertEqual(self.mapper.pos_to_wn('名詞-一般'), 'n')
        self.assertEqual(self.mapper.pos_to_wn('名詞-サ変接続'), 'n')
        self.assertEqual(self.mapper.pos_to_wn('名詞-数'), 'n')
    
    def test_verb_tags(self):
        """Test mapping of Japanese verb tags."""
        self.assertEqual(self.mapper.pos_to_wn('動詞-自立'), 'v')
    
    def test_adj_tags(self):
        """Test mapping of Japanese adjective tags."""
        self.assertEqual(self.mapper.pos_to_wn('形容詞-自立'), 'a')
        self.assertEqual(self.mapper.pos_to_wn('名詞-形容動詞語幹'), 'a')
        # Test exception for specific lemmas
        self.assertEqual(self.mapper.pos_to_wn('連体詞', 'その'), 'x')
    
    def test_adv_tags(self):
        """Test mapping of Japanese adverb tags."""
        self.assertEqual(self.mapper.pos_to_wn('副詞-一般'), 'r')
        self.assertEqual(self.mapper.pos_to_wn('副詞-助詞類接続'), 'r')
    
    def test_other_tags(self):
        """Test mapping of other Japanese tags."""
        self.assertEqual(self.mapper.pos_to_wn('助詞-格助詞'), 'x')
        self.assertEqual(self.mapper.pos_to_wn('助動詞'), 'x')
    
    def test_convenience_function(self):
        """Test the convenience function for mapping."""
        self.assertEqual(pos_to_wn('名詞-一般', 'jap'), 'n')
        self.assertEqual(pos_to_wn('動詞-自立', 'jap'), 'v')


class TestChineseMappings(unittest.TestCase):
    """Test Chinese POS mappings."""
    
    def setUp(self):
        """Set up the test case."""
        self.mapper = ChinesePOSMapper()
    
    def test_noun_tags(self):
        """Test mapping of Chinese noun tags."""
        self.assertEqual(self.mapper.pos_to_wn('NN'), 'n')
        self.assertEqual(self.mapper.pos_to_wn('NN2'), 'n')
        self.assertEqual(self.mapper.pos_to_wn('NR'), 'n')
        self.assertEqual(self.mapper.pos_to_wn('NT'), 'n')
    
    def test_verb_tags(self):
        """Test mapping of Chinese verb tags."""
        self.assertEqual(self.mapper.pos_to_wn('VV'), 'v')
        self.assertEqual(self.mapper.pos_to_wn('VV2'), 'v')
        self.assertEqual(self.mapper.pos_to_wn('VC'), 'v')
        self.assertEqual(self.mapper.pos_to_wn('VE'), 'v')
    
    def test_adj_tags(self):
        """Test mapping of Chinese adjective tags."""
        self.assertEqual(self.mapper.pos_to_wn('JJ'), 'a')
        self.assertEqual(self.mapper.pos_to_wn('JJ2'), 'a')
        self.assertEqual(self.mapper.pos_to_wn('VA'), 'a')
    
    def test_adv_tags(self):
        """Test mapping of Chinese adverb tags."""
        self.assertEqual(self.mapper.pos_to_wn('AD'), 'r')
        self.assertEqual(self.mapper.pos_to_wn('AD2'), 'r')
    
    def test_other_tags(self):
        """Test mapping of other Chinese tags."""
        self.assertEqual(self.mapper.pos_to_wn('CC'), 'x')
        self.assertEqual(self.mapper.pos_to_wn('P'), 'x')
    
    def test_convenience_function(self):
        """Test the convenience function for mapping."""
        self.assertEqual(pos_to_wn('NN', 'zsm'), 'n')
        self.assertEqual(pos_to_wn('VV', 'zsm'), 'v')


class TestVietnameseMappings(unittest.TestCase):
    """Test Vietnamese POS mappings."""
    
    def setUp(self):
        """Set up the test case."""
        self.mapper = VietnamesePOSMapper()
    
    def test_noun_tags(self):
        """Test mapping of Vietnamese noun tags."""
        self.assertEqual(self.mapper.pos_to_wn('N'), 'n')
        self.assertEqual(self.mapper.pos_to_wn('Np'), 'n')
        self.assertEqual(self.mapper.pos_to_wn('Nc'), 'n')
    
    def test_verb_tags(self):
        """Test mapping of Vietnamese verb tags."""
        self.assertEqual(self.mapper.pos_to_wn('V'), 'v')
    
    def test_adj_tags(self):
        """Test mapping of Vietnamese adjective tags."""
        self.assertEqual(self.mapper.pos_to_wn('A'), 'a')
    
    def test_adv_tags(self):
        """Test mapping of Vietnamese adverb tags."""
        self.assertEqual(self.mapper.pos_to_wn('L'), 'r')
        self.assertEqual(self.mapper.pos_to_wn('R'), 'r')
    
    def test_other_tags(self):
        """Test mapping of other Vietnamese tags."""
        self.assertEqual(self.mapper.pos_to_wn('C'), 'x')
        self.assertEqual(self.mapper.pos_to_wn('E'), 'x')
    
    def test_convenience_function(self):
        """Test the convenience function for mapping."""
        self.assertEqual(pos_to_wn('N', 'vie'), 'n')
        self.assertEqual(pos_to_wn('V', 'vie'), 'v')


class TestBaseMappings(unittest.TestCase):
    """Test base mapping functionality."""
    
    def test_get_pos_mapper(self):
        """Test getting POS mappers for different languages."""
        self.assertIsInstance(get_pos_mapper('eng'), EnglishPOSMapper)
        self.assertIsInstance(get_pos_mapper('ces'), CzechPOSMapper)
        self.assertIsInstance(get_pos_mapper('jap'), JapanesePOSMapper)
        self.assertIsInstance(get_pos_mapper('zsm'), ChinesePOSMapper)
        self.assertIsInstance(get_pos_mapper('vie'), VietnamesePOSMapper)
    
    def test_invalid_language(self):
        """Test behavior with invalid language codes."""
        with self.assertRaises(ValueError):
            get_pos_mapper('xyz')
    
    def test_global_pos_to_wn(self):
        """Test the global pos_to_wn function."""
        self.assertEqual(pos_to_wn('NN', 'eng'), 'n')
        self.assertEqual(pos_to_wn('NOUN', 'ces'), 'n')
        self.assertEqual(pos_to_wn('名詞-一般', 'jap'), 'n')
        self.assertEqual(pos_to_wn('NN', 'zsm'), 'n')
        self.assertEqual(pos_to_wn('N', 'vie'), 'n')


if __name__ == '__main__':
    unittest.main()
