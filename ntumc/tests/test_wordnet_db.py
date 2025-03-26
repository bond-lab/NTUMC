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
        print(f"Senses query results for 'happy': {results}")
        for result in results:
            print(f"Result: {result}")
        self.assertTrue(any('01148283-a' in synset for _, synset in results))

    def test_insert_word_existing(self):
        # Insert a word and get its ID
        word_id_1 = self.wn_manager.insert_word(lang='eng', word='happy', pos='a')
        # Insert the same word again and get its ID
        word_id_2 = self.wn_manager.insert_word(lang='eng', word='happy', pos='a')
        # Assert that the IDs are the same
        self.assertEqual(word_id_1, word_id_2)

    def test_insert_sense_existing(self):
        # Insert a sense and get its result
        word_id = self.wn_manager.insert_word(lang='eng', word='happy', pos='a')
        result_1 = self.wn_manager.insert_sense(synset='01148283-a', wordid=word_id, lang='eng', projectname='test_project')
        # Insert the same sense again and get its result
        result_2 = self.wn_manager.insert_sense(synset='01148283-a', wordid=word_id, lang='eng', projectname='test_project')
        # Assert that the results are the same
        self.assertEqual(result_1, result_2)
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

    def test_add_wn_script(self):
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
