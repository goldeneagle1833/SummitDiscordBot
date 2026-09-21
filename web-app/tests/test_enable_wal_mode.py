import sqlite3

import pytest

from migrations.enable_wal_mode import enable_wal_mode
from services.monitoring import _check_database


def _make_db(path):
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()


def test_switches_existing_dbs_and_skips_missing(tmp_path):
    db = tmp_path / "a.db"
    _make_db(db)

    modes = enable_wal_mode([db, tmp_path / "missing.db"])

    assert modes == {str(db): "wal"}
    assert not (tmp_path / "missing.db").exists()
    assert enable_wal_mode([db]) == {str(db): "wal"}


def _commit_during_open_read(db):
    """Commit a write while another connection is mid-read, then read again."""
    long_reader = sqlite3.connect(str(db), isolation_level=None)
    long_reader.execute("BEGIN")
    long_reader.execute("SELECT * FROM t").fetchall()
    try:
        writer = sqlite3.connect(str(db), timeout=0)
        writer.execute("INSERT INTO t VALUES (2)")
        writer.commit()
        writer.close()
    finally:
        long_reader.execute("COMMIT")
        long_reader.close()


def test_rollback_mode_reproduces_lock(tmp_path):
    db = tmp_path / "a.db"
    _make_db(db)

    with pytest.raises(sqlite3.OperationalError, match="locked"):
        _commit_during_open_read(db)


def test_wal_lets_writes_commit_during_long_reads(tmp_path):
    db = tmp_path / "a.db"
    _make_db(db)
    enable_wal_mode([db])

    _commit_during_open_read(db)

    ok, status, _ = _check_database(db)
    assert (ok, status) == (True, "ok")
    conn = sqlite3.connect(str(db))
    assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 2
    conn.close()
