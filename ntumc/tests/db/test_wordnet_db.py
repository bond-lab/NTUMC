import unittest
from ntumc.db.wordnet_db import WordNetManager

class TestWordNetManager(unittest.TestCase):
    def setUp(self):
        # Path to the test database
        self.db_path = 'test_resources/wn-ntumc.db'
        self.manager = WordNetManager(self.db_path)

    def tearDown(self):
        self.manager.close()

    def test_connect(self):
        """Test establishing a connection to the database."""
        self.manager.connect()
        self.assertIsNotNone(self.manager.conn)

    def test_Senses(self):
        """Test querying senses for a given lemma."""
        synsets = self.manager.Senses('eng', lemma='newt')
        self.assertIsInstance(synsets, list)
        self.assertEqual(synsets, [('newt', '01630284-n')], 
                     f"Expected [('newt', '01630284-n')] but got {synsets}")

    def test_Senses_Other_Language(self):
        """Test querying synsets for a lemma in another language."""
        # Example for Czech
        synsets = self.manager.Senses('ces', lemma='mlok')
        self.assertIsInstance(synsets, list)
        self.assertEqual(synsets, [('mlok', '01629276-n')],  
                         f"Expected [[('mlok', '01629276-n')] but got {synsets}")


if __name__ == '__main__':
    unittest.main()
