"""Durable conservative accounting and portable process exclusion.

Reservations/outcomes are the source of truth (frozen424_repair lineage).
SQLite is only a local mutex, not a mutable results or billing database.
"""
from contextlib import contextmanager
import os
import sqlite3
from .contracts import HumanWillError, require


@contextmanager
def writer(root):
    path = root / 'writer.sqlite'
    require(not path.is_symlink(), "unsafe_path", "Unsafe lock path.")
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600); os.close(fd)
    except FileExistsError: pass
    connection = sqlite3.connect(path, timeout=0)
    try:
        try: connection.execute('BEGIN IMMEDIATE')
        except sqlite3.OperationalError:
            raise HumanWillError('run_busy', 'Another process is executing this run.') from None
        yield
    finally:
        connection.rollback(); connection.close()


def accounting(attempts):
    total, unknown = 0, 0
    for attempt in attempts:
        reserved = attempt['intent']['reserved_micro_usd']
        outcome = attempt.get('outcome')
        cost = outcome['accounting']['accounted_micro_usd'] if outcome else reserved
        total += cost
        if not outcome or outcome['accounting']['kind'] == 'unknown_hold': unknown += cost
    return {'accounted_micro_usd': total, 'unknown_hold_micro_usd': unknown}
