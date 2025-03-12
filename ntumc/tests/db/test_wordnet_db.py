import unittest
from ntumc.db.wordnet_db import WordNetManager

class TestWordNetManager(unittest.TestCase):
    def setUp(self):
        # Path to the test database
        self.db_path = '../../../test_resources/wn-ntumc.db'
        self.manager = WordNetManager(self.db_path)

    def tearDown(self):
        self.manager.close()

    def test_connect(self):
        """Test establishing a connection to the database."""
        self.manager.connect()
        self.assertIsNotNone(self.manager.conn)

    def test_query_synsets(self):
        """Test querying synsets for a given lemma."""
        synsets = self.manager.query_synsets('example_lemma')
        self.assertIsInstance(synsets, list)

    def test_get_synset_definitions(self):
        """Test retrieving definitions for a given synset ID."""
        definitions = self.manager.get_synset_definitions('example_synset_id')
        self.assertIsInstance(definitions, list)

    def test_get_lemmas_for_synset(self):
        """Test retrieving lemmas for a given synset ID."""
        lemmas = self.manager.get_lemmas_for_synset('example_synset_id')
        self.assertIsInstance(lemmas, list)

if __name__ == '__main__':
    unittest.main()
