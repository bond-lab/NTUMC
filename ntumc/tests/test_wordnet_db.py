import unittest
import os
from pathlib import Path
from unittest import mock
from ntumc.db.wordnet_db import WordNetManager
from ntumc.wordnet.add_wn import main as add_wn_main

class TestWordNetDB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Set up the test database
        cls.test_db_path = Path(__file__).parent / "fixtures" / "wn_test.db"
        if not cls.test_db_path.exists():
            from ntumc.tests.fixtures.create_test_wordnet_db import create_test_wordnet_db
            create_test_wordnet_db(cls.test_db_path)

    def setUp(self):
        self.wn_manager = WordNetManager(str(self.test_db_path))
        self.wn_manager.connect()

    def tearDown(self):
        self.wn_manager.close()

    def test_senses_query(self):
        """Test querying senses for a given lemma."""
        results = self.wn_manager.Senses(lang='eng', lemma='happy')
        print(f"Senses query results for 'happy': {results}")
        for result in results:
            print(f"Result: {result}")
        self.assertTrue(any('01148283-a' in synset for _, synset in results))

    def test_insert_word_existing(self):
        """Test that inserting an existing word returns the same ID."""
        word_id_1 = self.wn_manager.insert_word(lang='eng', word='happy', pos='a')
        # Insert the same word again and get its ID
        word_id_2 = self.wn_manager.insert_word(lang='eng', word='happy', pos='a')
        # Assert that the IDs are the same
        self.assertEqual(word_id_1, word_id_2)

    def test_insert_sense_existing(self):
        """Test that inserting an existing sense does not create duplicates."""
        word_id = self.wn_manager.insert_word(lang='eng', word='happy', pos='a')
        result_1 = self.wn_manager.insert_sense(synset='01148283-a', wordid=word_id, lang='eng', projectname='test_project')
        # Insert the same sense again and verify no duplicates
        cursor = self.wn_manager.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM sense WHERE synset = ? AND wordid = ? AND lang = ?",
            ('01148283-a', word_id, 'eng')
        )
        count_before = cursor.fetchone()[0]
        result_2 = self.wn_manager.insert_sense(synset='01148283-a', wordid=word_id, lang='eng', projectname='test_project')
        cursor.execute(
            "SELECT COUNT(*) FROM sense WHERE synset = ? AND wordid = ? AND lang = ?",
            ('01148283-a', word_id, 'eng')
        )
        count_after = cursor.fetchone()[0]
        self.assertEqual(count_before, count_after)
        # Test the add_wn script
        wnfile = str(Path(__file__).parent / "fixtures" / "wn_test_eng.tab")
        dbfile = str(self.test_db_path)
        args = ['add_wn.py', wnfile, 'eng', 'test_project', dbfile, '--delete-old']
        with unittest.mock.patch('sys.argv', args):
            add_wn_main()

        # Verify that data was added
        results = self.wn_manager.Senses(lang='eng', lemma='newt')
        print(f"Senses query results for 'newt': {results}")
        for result in results:
            print(f"Result: {result}")
        self.assertTrue(any('01630284-n' in synset for _, synset in results))

if __name__ == "__main__":
    unittest.main()
import unittest
import os
from pathlib import Path
from unittest import mock
from ntumc.db.wordnet_db import WordNetManager
from ntumc.wordnet.add_wn import main as add_wn_main

class TestWordNetDB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Set up the test database
        cls.test_db_path = Path(__file__).parent / "fixtures" / "wn_test.db"
        if not cls.test_db_path.exists():
            from ntumc.tests.fixtures.create_test_wordnet_db import create_test_wordnet_db
            create_test_wordnet_db(cls.test_db_path)

    def setUp(self):
        self.wn_manager = WordNetManager(str(self.test_db_path))
        self.wn_manager.connect()

    def tearDown(self):
        self.wn_manager.close()

    def test_senses_query(self):
        # Test querying senses
        results = self.wn_manager.Senses(lang='eng', lemma='happy')
        self.assertTrue(any('01148283-a' in synset for _, synset in results))

    def test_insert_word_existing(self):
        # Insert a word and get its ID
        word_id_1 = self.wn_manager.insert_word(lang='eng', word='happy', pos='a')
        # Insert the same word again and get its ID
        word_id_2 = self.wn_manager.insert_word(lang='eng', word='happy', pos='a')
        # Assert that the IDs are the same
        self.assertEqual(word_id_1, word_id_2)

    def test_insert_sense_existing(self):
        # Insert a sense and verify its existence
        word_id = self.wn_manager.insert_word(lang='eng', word='happy', pos='a')
        result_1 = self.wn_manager.insert_sense(synset='01148283-a', wordid=word_id, lang='eng', projectname='test_project')
        # Insert the same sense again and get its result
        result_2 = self.wn_manager.insert_sense(synset='01148283-a', wordid=word_id, lang='eng', projectname='test_project')
        # Assert that the results are the same
        self.assertEqual(result_1, result_2)

    def test_add_definition(self):
        """Test adding a definition to a synset."""
        synset = '01148283-a'
        definition = 'Feeling or showing pleasure or contentment.'
        self.wn_manager.update_synset_def(synset=synset, lang='eng', definition=definition, sid='1')
        
        cursor = self.wn_manager.conn.cursor()
        cursor.execute("SELECT def FROM synset_def WHERE synset = ? AND lang = ?", (synset, 'eng'))
        result = cursor.fetchone()
        self.assertIsNotNone(result)
        self.assertEqual(result[0], definition)

    def test_add_example(self):
        """Test adding an example to a synset."""
        synset = '01148283-a'
        example = 'She felt happy about the news.'
        self.wn_manager.update_synset_ex(synset=synset, lang='eng', example=example, sid='1')
        
        cursor = self.wn_manager.conn.cursor()
        cursor.execute("SELECT def FROM synset_ex WHERE synset = ? AND lang = ?", (synset, 'eng'))
        result = cursor.fetchone()
        self.assertIsNotNone(result)
        self.assertEqual(result[0], example)

    def test_add_words_different_languages(self):
        """Test adding words in different languages."""
        # Czech
        word_id_cz = self.wn_manager.insert_word(lang='ces', word='šťastný', pos='a')
        self.assertIsNotNone(word_id_cz)

        # Japanese
        word_id_ja = self.wn_manager.insert_word(lang='jpn', word='幸せ', pos='a')
        self.assertIsNotNone(word_id_ja)
        """Test the add_wn script for adding WordNet data."""
        wnfile = str(Path(__file__).parent / "fixtures" / "wn_test_eng.tab")
        dbfile = str(self.test_db_path)
        args = ['add_wn.py', wnfile, 'eng', 'test_project', dbfile, '--delete-old']
        with unittest.mock.patch('sys.argv', args):
            add_wn_main()

        # Verify that data was added
        results = self.wn_manager.Senses(lang='eng', lemma='newt')
        print(f"Senses query results for 'newt': {results}")
        for result in results:
            print(f"Result: {result}")          
        
        self.assertTrue(any('01630284-n' in synset for _, synset in results))

if __name__ == "__main__":
    unittest.main()
