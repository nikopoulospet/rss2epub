import json
import tempfile
import unittest
from pathlib import Path

from rss2rm.state import State


class TestState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = str(Path(self.tmp) / "synced.json")

    def test_new_id_not_synced(self):
        s = State(self.state_path)
        self.assertFalse(s.is_synced("id-1"))

    def test_mark_synced_persists(self):
        s = State(self.state_path)
        s.mark_synced("id-1")
        s2 = State(self.state_path)
        self.assertTrue(s2.is_synced("id-1"))

    def test_multiple_ids_independent(self):
        s = State(self.state_path)
        s.mark_synced("id-1")
        self.assertTrue(s.is_synced("id-1"))
        self.assertFalse(s.is_synced("id-2"))

    def test_write_is_atomic_via_tmp_file(self):
        s = State(self.state_path)
        s.mark_synced("id-1")
        tmp_path = Path(self.state_path).with_suffix(".tmp")
        self.assertFalse(tmp_path.exists(), ".tmp file should be cleaned up after write")

    def test_loads_existing_state(self):
        path = Path(self.state_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"synced": ["pre-existing-id"]}))
        s = State(self.state_path)
        self.assertTrue(s.is_synced("pre-existing-id"))
        self.assertFalse(s.is_synced("other-id"))

    def test_missing_file_starts_empty(self):
        s = State(str(Path(self.tmp) / "does-not-exist" / "synced.json"))
        self.assertFalse(s.is_synced("anything"))
