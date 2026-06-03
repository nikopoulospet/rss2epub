import tempfile
import unittest
from pathlib import Path

from rss2rm.localdir import LocalDirUploader


class TestLocalDirUploader(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_upload_writes_file(self):
        ul = LocalDirUploader(self.tmp)
        result = ul.upload("test.epub", b"fake epub data")
        self.assertTrue(result)
        self.assertEqual((Path(self.tmp) / "test.epub").read_bytes(), b"fake epub data")

    def test_creates_directory_if_missing(self):
        new_dir = str(Path(self.tmp) / "subdir" / "output")
        ul = LocalDirUploader(new_dir)
        ul.upload("a.epub", b"data")
        self.assertTrue((Path(new_dir) / "a.epub").exists())

    def test_overwrites_existing_file(self):
        ul = LocalDirUploader(self.tmp)
        ul.upload("f.epub", b"first")
        ul.upload("f.epub", b"second")
        self.assertEqual((Path(self.tmp) / "f.epub").read_bytes(), b"second")
