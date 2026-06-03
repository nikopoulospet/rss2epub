import json
import os
from pathlib import Path


class State:
    def __init__(self, path: str) -> None:
        self.path = Path(path).expanduser()
        self._synced: set[str] = self._load()

    def is_synced(self, article_id: str) -> bool:
        return article_id in self._synced

    def mark_synced(self, article_id: str) -> None:
        self._synced.add(article_id)
        self._save()

    def _load(self) -> set[str]:
        if self.path.exists():
            with open(self.path) as f:
                return set(json.load(f).get("synced", []))
        return set()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump({"synced": list(self._synced)}, f)
        os.replace(tmp, self.path)
