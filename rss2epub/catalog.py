import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CatalogRow:
    item_id: str
    content_hash: str
    filename: str
    title: str | None
    published: int | None
    last_seen: int
    last_written: int


class Catalog:
    def __init__(self, db_path: str) -> None:
        self.path = Path(db_path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._migrate()

    def _migrate(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                item_id      TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL,
                filename     TEXT NOT NULL,
                title        TEXT,
                published    INTEGER,
                last_seen    INTEGER NOT NULL,
                last_written INTEGER NOT NULL
            )
        """)
        self._conn.commit()

    def lookup(self, item_id: str) -> CatalogRow | None:
        row = self._conn.execute(
            "SELECT item_id, content_hash, filename, title, published, last_seen, last_written "
            "FROM articles WHERE item_id = ?",
            (item_id,),
        ).fetchone()
        return CatalogRow(*row) if row else None

    def upsert(self, row: CatalogRow) -> None:
        """Insert or update a row. The EPUB must be on disk before calling this."""
        self._conn.execute(
            """
            INSERT INTO articles
                (item_id, content_hash, filename, title, published, last_seen, last_written)
            VALUES
                (:item_id, :content_hash, :filename, :title, :published, :last_seen, :last_written)
            ON CONFLICT(item_id) DO UPDATE SET
                content_hash  = excluded.content_hash,
                filename      = excluded.filename,
                title         = excluded.title,
                last_seen     = excluded.last_seen,
                last_written  = excluded.last_written
            """,
            {
                "item_id": row.item_id,
                "content_hash": row.content_hash,
                "filename": row.filename,
                "title": row.title,
                "published": row.published,
                "last_seen": row.last_seen,
                "last_written": row.last_written,
            },
        )
        self._conn.commit()

    def touch(self, item_id: str, last_seen: int) -> None:
        """Update last_seen for an article whose content has not changed."""
        self._conn.execute(
            "UPDATE articles SET last_seen = ? WHERE item_id = ?",
            (last_seen, item_id),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
