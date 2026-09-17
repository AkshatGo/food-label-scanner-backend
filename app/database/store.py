"""Storage layer: MongoDB when available, in-memory otherwise.

The LabelLens data model (scans, products, users) is served identically by
either backend so the API never depends on an external database to run.
"""

import itertools
import threading
from datetime import datetime, timezone

from .. import config

_lock = threading.Lock()


class InMemoryCollection:
    """A pymongo-like collection backed by a dict. Thread-safe, dev-only."""

    _ids = itertools.count(1)

    def __init__(self):
        self._docs = {}
        self._seq = itertools.count(1)

    # --- writes ---------------------------------------------------------
    def insert_one(self, document):
        with _lock:
            doc_id = next(self._seq)
            stored = dict(document)
            stored["_id"] = doc_id
            self._docs[doc_id] = stored
            return type("InsertOneResult", (), {"inserted_id": doc_id})()

    def update_one(self, query, update):
        with _lock:
            doc = self._find_one_unlocked(query)
            if doc is None:
                return type("UpdateResult", (), {"matched_count": 0, "modified_count": 0})()
            self._apply_update(doc, update)
            return type("UpdateResult", (), {"matched_count": 1, "modified_count": 1})()

    def delete_one(self, query):
        with _lock:
            doc = self._find_one_unlocked(query)
            if doc is None:
                return type("DeleteResult", (), {"deleted_count": 0})()
            del self._docs[doc["_id"]]
            return type("DeleteResult", (), {"deleted_count": 1})()

    # --- reads ----------------------------------------------------------
    def find_one(self, query):
        with _lock:
            return self._find_one_unlocked(query)

    def find(self, query=None):
        query = query or {}
        with _lock:
            return [dict(doc) for doc in self._docs.values() if self._matches(doc, query)]

    # --- internals ------------------------------------------------------
    @staticmethod
    def _matches(doc, query):
        for key, expected in query.items():
            value = doc
            for part in key.split("."):
                if not isinstance(value, dict) or part not in value:
                    return False
                value = value[part]
            if value != expected:
                return False
        return True

    def _find_one_unlocked(self, query):
        for doc in self._docs.values():
            if self._matches(doc, query):
                return doc
        return None

    @staticmethod
    def _apply_update(doc, update):
        set_data = update.get("$set", {})
        for key, value in set_data.items():
            target = doc
            parts = key.split(".")
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value
        for key, value in update.get("$unset", {}).items():
            parts = key.split(".")
            target = doc
            for part in parts[:-1]:
                if not isinstance(target, dict):
                    break
                target = target.get(part, {})
            if isinstance(target, dict):
                target.pop(parts[-1], None)


class _MongoCollectionAdapter:
    """Normalizes pymongo results for internal use."""

    def __init__(self, collection):
        self._collection = collection

    def insert_one(self, document):
        return self._collection.insert_one(dict(document))

    def update_one(self, query, update):
        return self._collection.update_one(query, update)

    def delete_one(self, query):
        return self._collection.delete_one(query)

    def find_one(self, query):
        return self._collection.find_one(query)

    def find(self, query=None):
        return self._collection.find(query or {})


def _build_mongo():
    import certifi
    from pymongo import MongoClient

    client = MongoClient(
        config.MONGODB_URI,
        tls=True,
        tlsCAFile=certifi.where(),
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
    )
    client.admin.command("ping")
    db = client[config.DATABASE_NAME]
    return client, db


mongo_client = None
mongo_db = None
_backend = "memory"

if config.MONGODB_URI:
    try:
        mongo_client, mongo_db = _build_mongo()
        _backend = "mongodb"
    except Exception:  # noqa: BLE001 - fall back gracefully at import time
        mongo_client = None
        mongo_db = None
        _backend = "memory"

if _backend == "mongodb":
    scans = _MongoCollectionAdapter(mongo_db["scans"])
    users = _MongoCollectionAdapter(mongo_db["users"])
    products = _MongoCollectionAdapter(mongo_db["products"])
    fs = __import__("gridfs", fromlist=["GridFS"]).GridFS(mongo_db)
else:
    scans = InMemoryCollection()
    users = InMemoryCollection()
    products = InMemoryCollection()

    class _MemoryGridFS:
        """Minimal GridFS-like store for local development."""

        def __init__(self):
            self._files = {}
            self._seq = itertools.count(1)

        def put(self, data, filename=None, metadata=None, **_kwargs):
            file_id = next(self._seq)
            self._files[file_id] = {
                "data": bytes(data),
                "filename": filename,
                "metadata": metadata or {},
            }
            return file_id

        def get(self, file_id):
            import io

            record = self._files.get(file_id)
            if record is None:
                from gridfs.errors import NoFile

                raise NoFile(f"No file with id {file_id}")
            return io.BytesIO(record["data"])

        def delete(self, file_id):
            self._files.pop(file_id, None)

    fs = _MemoryGridFS()


def storage_backend() -> str:
    return _backend


def test_connection() -> bool:
    """Ping the storage backend; raises if unavailable."""
    if _backend == "mongodb":
        mongo_client.admin.command("ping")
    return True


def utcnow():
    return datetime.now(timezone.utc)
