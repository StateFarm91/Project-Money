"""Route nested knowledge-evidence reads through the caller's transaction.

This adapter provides transaction composition only. It does not lock evidence
or provide an authority fence, and is intended only for read-only operations.
"""
from contextlib import contextmanager


class _ReadSessionDatabase:
    def __init__(self, db, session):
        bind = session.get_bind()
        if getattr(bind, "engine", bind) is not db.engine:
            raise ValueError("knowledge read session is not bound to this database")
        if not session.in_transaction():
            raise ValueError("knowledge read session requires an active transaction")
        if session.new or session.dirty or session.deleted:
            raise ValueError("knowledge read session has pending ORM changes")
        connection = session.connection()
        if connection.dialect.name == "postgresql":
            isolation = connection.exec_driver_sql("SHOW transaction_isolation").scalar_one()
            if isolation.lower() != "read committed":
                raise ValueError("knowledge read session requires READ COMMITTED on PostgreSQL")
        # A caller may have loaded an old rule before acquiring its fence.
        # Drop cached attributes before evidence reads; never discard tracked
        # edits, which were refused above. A transaction's isolation level and
        # the authority fence still determine what the database can see.
        session.expire_all()
        self._db = db
        self._session = session

    @contextmanager
    def session(self):
        # Ownership, commit, rollback and closure remain with the caller.
        yield self._session

    def __getattr__(self, name):
        return getattr(self._db, name)


def bind_read_session(db, session):
    return db if session is None else _ReadSessionDatabase(db, session)
