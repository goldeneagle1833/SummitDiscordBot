"""SQLite connection helpers.

Use ``get_conn`` as a context manager so connections are always closed and
transactions are committed on success / rolled back on error.

Example:
    from utils.db import get_conn

    with get_conn(MATCH_RECORDS_DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1")

For read-only queries pass ``commit=False`` (default is True for writes).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Union

PathLike = Union[str, Path]


@contextmanager
def get_conn(
    db_path: PathLike,
    *,
    row_factory: bool = False,
    timeout: float = 30.0,
) -> Iterator[sqlite3.Connection]:
    """Yield a sqlite3 connection. Commits on clean exit, rolls back on error.

    Args:
        db_path: Path to the sqlite database file.
        row_factory: If True, sets ``conn.row_factory = sqlite3.Row`` so rows
            can be accessed by column name.
        timeout: Seconds to wait when the database is locked.
    """
    conn = sqlite3.connect(str(db_path), timeout=timeout)
    if row_factory:
        conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
