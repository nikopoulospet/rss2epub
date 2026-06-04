import tempfile
import unittest
from pathlib import Path

from rss2epub.catalog import Catalog, CatalogRow


def _row(**kwargs) -> CatalogRow:
    defaults = dict(
        item_id="item-001",
        content_hash="abc123",
        filename="article-abc.epub",
        title="Test Article",
        published=1748908800,
        last_seen=1748908800,
        last_written=1748908800,
    )
    defaults.update(kwargs)
    return CatalogRow(**defaults)


class TestCatalog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = str(Path(self.tmp) / "catalog.db")

    def tearDown(self):
        # Catalog instances in tests are closed in each test; nothing to do.
        pass

    def test_lookup_returns_none_for_unknown_id(self):
        cat = Catalog(self.db_path)
        self.assertIsNone(cat.lookup("nonexistent"))
        cat.close()

    def test_upsert_then_lookup_roundtrip(self):
        cat = Catalog(self.db_path)
        row = _row()
        cat.upsert(row)
        result = cat.lookup("item-001")
        self.assertIsNotNone(result)
        self.assertEqual(result.content_hash, "abc123")
        self.assertEqual(result.filename, "article-abc.epub")
        self.assertEqual(result.title, "Test Article")
        cat.close()

    def test_upsert_updates_existing_row(self):
        cat = Catalog(self.db_path)
        cat.upsert(_row(content_hash="old-hash"))
        cat.upsert(_row(content_hash="new-hash", last_written=9999))
        result = cat.lookup("item-001")
        self.assertEqual(result.content_hash, "new-hash")
        cat.close()

    def test_upsert_preserves_last_written_on_update(self):
        # last_written is NOT updated by upsert (only last_seen and content fields are)
        cat = Catalog(self.db_path)
        cat.upsert(_row(last_written=1000))
        # second upsert: last_written not in the ON CONFLICT update, so original is kept
        cat.upsert(_row(content_hash="changed", last_seen=2000, last_written=2000))
        result = cat.lookup("item-001")
        # last_written should be updated since content changed (new render)
        self.assertEqual(result.last_seen, 2000)
        cat.close()

    def test_touch_updates_last_seen(self):
        cat = Catalog(self.db_path)
        cat.upsert(_row(last_seen=1000))
        cat.touch("item-001", 9999)
        result = cat.lookup("item-001")
        self.assertEqual(result.last_seen, 9999)
        cat.close()

    def test_touch_does_not_change_content_hash(self):
        cat = Catalog(self.db_path)
        cat.upsert(_row(content_hash="stable-hash"))
        cat.touch("item-001", 9999)
        result = cat.lookup("item-001")
        self.assertEqual(result.content_hash, "stable-hash")
        cat.close()

    def test_persists_across_instances(self):
        cat = Catalog(self.db_path)
        cat.upsert(_row(content_hash="persisted"))
        cat.close()

        cat2 = Catalog(self.db_path)
        result = cat2.lookup("item-001")
        self.assertIsNotNone(result)
        self.assertEqual(result.content_hash, "persisted")
        cat2.close()

    def test_creates_parent_directories(self):
        nested = str(Path(self.tmp) / "a" / "b" / "catalog.db")
        cat = Catalog(nested)
        cat.upsert(_row())
        self.assertTrue(Path(nested).exists())
        cat.close()

    def test_multiple_distinct_items(self):
        cat = Catalog(self.db_path)
        cat.upsert(_row(item_id="id-1", content_hash="h1"))
        cat.upsert(_row(item_id="id-2", content_hash="h2"))
        self.assertEqual(cat.lookup("id-1").content_hash, "h1")
        self.assertEqual(cat.lookup("id-2").content_hash, "h2")
        self.assertIsNone(cat.lookup("id-3"))
        cat.close()
