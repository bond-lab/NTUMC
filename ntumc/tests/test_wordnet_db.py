import shutil
import tempfile
import unittest
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
            from ntumc.tests.fixtures.create_test_wordnet_db import (
                create_test_wordnet_db,
            )

            create_test_wordnet_db(cls.test_db_path)

    def setUp(self):
        # Work on a per-test copy so no test can mutate the tracked fixture.
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        self.tmp_db_path = str(Path(tmpdir) / "wn_test.db")
        shutil.copy2(self.test_db_path, self.tmp_db_path)

        self.wn_manager = WordNetManager(self.tmp_db_path)
        self.wn_manager.connect()
        self.addCleanup(self.wn_manager.close)

    def _run_add_wn(self, wnfile: str, lang: str, args_tail: list[str] | None = None):
        """Run add_wn.py against this test's isolated copy of the fixture DB."""
        args = [
            "add_wn.py",
            self.tmp_db_path,
            lang,
            "test_project",
            wnfile,
            *(args_tail or []),
        ]
        with mock.patch("sys.argv", args):
            add_wn_main()

    def test_senses_query(self):
        """Test querying senses for a given lemma."""
        results = self.wn_manager.Senses(lang="eng", lemma="happy")
        self.assertTrue(any("01148283-a" in synset for _, synset in results))

    def test_insert_word_existing(self):
        """Test that inserting an existing word returns the same ID."""
        word_id_1 = self.wn_manager.insert_word(lang="eng", word="happy", pos="a")
        # Insert the same word again and get its ID
        word_id_2 = self.wn_manager.insert_word(lang="eng", word="happy", pos="a")
        # Assert that the IDs are the same
        self.assertEqual(word_id_1, word_id_2)

    def test_insert_sense_existing(self):
        """Test that inserting an existing sense does not create duplicates."""
        word_id = self.wn_manager.insert_word(lang="eng", word="happy", pos="a")
        self.wn_manager.insert_sense(
            synset="01148283-a", wordid=word_id, lang="eng", projectname="test_project"
        )
        cursor = self.wn_manager.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM sense WHERE synset = ? AND wordid = ? AND lang = ?",
            ("01148283-a", word_id, "eng"),
        )
        count_before = cursor.fetchone()[0]
        self.wn_manager.insert_sense(
            synset="01148283-a", wordid=word_id, lang="eng", projectname="test_project"
        )
        cursor.execute(
            "SELECT COUNT(*) FROM sense WHERE synset = ? AND wordid = ? AND lang = ?",
            ("01148283-a", word_id, "eng"),
        )
        count_after = cursor.fetchone()[0]
        self.assertEqual(count_before, count_after)

    def test_add_definition(self):
        """Test adding a definition to a synset."""
        synset = "01148283-a"
        definition = "Feeling or showing pleasure or contentment."
        self.wn_manager.update_synset_def(
            synset=synset, lang="eng", definition=definition, sid="1"
        )

        cursor = self.wn_manager.conn.cursor()
        cursor.execute(
            "SELECT def FROM synset_def WHERE synset = ? AND lang = ?", (synset, "eng")
        )
        result = cursor.fetchone()
        self.assertIsNotNone(result)
        self.assertEqual(result[0], definition)

    def test_add_example(self):
        """Test adding an example to a synset."""
        synset = "01148283-a"
        example = "She felt happy about the news."
        self.wn_manager.update_synset_ex(
            synset=synset, lang="eng", example=example, sid="1"
        )

        cursor = self.wn_manager.conn.cursor()
        cursor.execute(
            "SELECT def FROM synset_ex WHERE synset = ? AND lang = ?", (synset, "eng")
        )
        result = cursor.fetchone()
        self.assertIsNotNone(result)
        self.assertEqual(result[0], example)

    def test_add_words_different_languages(self):
        """Test adding words in different languages."""
        # Czech
        word_id_cz = self.wn_manager.insert_word(lang="ces", word="šťastný", pos="a")
        self.assertIsNotNone(word_id_cz)

        # Japanese
        word_id_ja = self.wn_manager.insert_word(lang="jpn", word="幸せ", pos="a")
        self.assertIsNotNone(word_id_ja)

    def test_add_wn_script(self):
        """Test the add_wn script for adding WordNet data."""
        wnfile = str(Path(__file__).parent / "fixtures" / "wn_test_eng.tab")
        self._run_add_wn(wnfile, "eng", ["--delete-old"])

        results = self.wn_manager.Senses(lang="eng", lemma="newt")
        self.assertTrue(("newt", "01630284-n") in results)

        results = self.wn_manager.Senses(lang="eng", lemma="ugh")
        self.assertTrue(("ugh", "76000004-x") in results)

    def test_add_wn_script_czech(self):
        """Test the add_wn script for adding WordNet data in a different language."""
        wnfile = str(Path(__file__).parent / "fixtures" / "wn_test_ces.tab")
        self._run_add_wn(wnfile, "ces")

        results = self.wn_manager.Senses(lang="ces", lemma="mlok")
        self.assertTrue(("mlok", "01630284-n") in results)

        results = self.wn_manager.Senses(lang="ces", lemma="šťastný")
        self.assertTrue(("šťastný", "01148283-a") in results)


if __name__ == "__main__":
    unittest.main()
