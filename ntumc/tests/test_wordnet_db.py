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
        self.assertTrue(any('01630284-n' in synset for _, synset in results))

if __name__ == "__main__":
    unittest.main()
