"""Lưu trữ JSON file — thay thế MongoDB, dữ liệu nằm trong thư mục data/.

Giữ giao diện quen thuộc giống Motor (db["collection"] -> find_one/find/insert_one/
update_one/delete_one/count_documents/...), dot-path trong key và $set được hỗ trợ.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config import load_config


# ---------------------------------------------------------------
# Tuần tự hóa datetime
# ---------------------------------------------------------------

def _serialize(value: Any) -> Any:
    """Chuyển datetime thành {"$date": iso} để JSON lưu được."""
    if isinstance(value, datetime):
        return {"$date": value.isoformat()}
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value


def _deserialize(value: Any) -> Any:
    """Khôi phục datetime từ {"$date": iso}."""
    if isinstance(value, dict):
        if set(value) == {"$date"}:
            return datetime.fromisoformat(value["$date"])
        return {k: _deserialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deserialize(v) for v in value]
    return value


def _get_path(doc: dict[str, Any], key: str) -> Any:
    """Đọc giá trị theo key có thể chứa dấu chấm (vd 'automod.anti_spam.enabled')."""
    cur: Any = doc
    for part in key.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _set_path(doc: dict[str, Any], key: str, value: Any) -> None:
    """Ghi giá trị theo key có dấu chấm, tự tạo dict trung gian."""
    parts = key.split(".")
    cur = doc
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _sort_value(value: Any) -> tuple[int, Any]:
    """Chuẩn hoá giá trị thành khoá so sánh được.

    Bảng xếp hạng sắp theo 'total_xp' vốn có thể vắng mặt (None) ở một số
    document, nếu so sánh thẳng int với None/str sẽ ném TypeError.
    Nhóm ưu tiên: None (0) < số (1) < chuỗi (2).
    """
    if value is None:
        return (0, 0)
    if isinstance(value, bool):
        return (1, int(value))
    if isinstance(value, (int, float)):
        return (1, value)
    return (2, str(value))


# ---------------------------------------------------------------
# Collection
# ---------------------------------------------------------------

class JsonCursor:
    """Cursor giả lập (hỗ trợ .sort() + async to_list()) như Motor."""

    def __init__(self, collection: "JsonCollection", query: dict[str, Any]) -> None:
        self._collection = collection
        self._query = query
        self._sort_keys: list[tuple[str, int]] = []

    def sort(self, key: str | tuple[str, ...], direction: int = 1) -> "JsonCursor":
        """Sắp xếp theo 1 key, hoặc nhiều key (tuple) theo thứ tự ưu tiên."""
        keys = (key,) if isinstance(key, str) else tuple(key)
        self._sort_keys = [(k, direction) for k in keys]
        return self

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        items = await self._collection._find(self._query)
        # Sắp xếp từ key ít ưu tiên nhất để sort() ổn định cho key trước đó.
        for sort_key, direction in reversed(self._sort_keys):
            items.sort(
                key=lambda d: _sort_value(_get_path(d, sort_key)),
                reverse=direction < 0,
            )
        if length is not None and length >= 0:
            return items[:length]
        return items


class _WriteResult:
    def __init__(self, matched: int = 0, modified: int = 0, upserted: Any = None) -> None:
        self.matched_count = matched
        self.modified_count = modified
        self.upserted_id = upserted

    @property
    def deleted_count(self) -> int:
        return 0


class _DeleteResult:
    def __init__(self, deleted: int = 0) -> None:
        self.deleted_count = deleted


class _InsertResult:
    def __init__(self, inserted_id: Any) -> None:
        self.inserted_id = inserted_id


class JsonCollection:
    """Một collection = một file JSON trong data/."""

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self._lock = asyncio.Lock()
        self._data: list[dict[str, Any]] = []
        self._load()

    # ----- I/O -----
    def _load(self) -> None:
        if self.file_path.exists():
            try:
                raw = json.loads(self.file_path.read_text(encoding="utf-8"))
                self._data = [_deserialize(doc) for doc in raw]
                return
            except (json.JSONDecodeError, OSError):
                pass
        self._data = []

    def _save(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [_serialize(doc) for doc in self._data]
        tmp = self.file_path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self.file_path)

    # ----- Query -----
    @staticmethod
    def _is_operator_expr(expected: Any) -> bool:
        """Dict chỉ chứa toán tử $xxx mới được hiểu là điều kiện, còn lại là so sánh bằng."""
        return (
            isinstance(expected, dict)
            and bool(expected)
            and all(isinstance(k, str) and k.startswith("$") for k in expected)
        )

    @staticmethod
    def _match_operators(actual: Any, expected: Any) -> bool:
        """So khớp một giá trị với điều kiện dạng toán tử Mongo ($gt, $ne...)."""
        if not JsonCollection._is_operator_expr(expected):
            return actual == expected

        for op, operand in expected.items():
            if op == "$in":
                if actual not in operand:
                    return False
            elif op == "$nin":
                if actual in operand:
                    return False
            elif op == "$ne":
                if actual == operand:
                    return False
            elif op == "$exists":
                if (actual is not None) != bool(operand):
                    return False
            # So sánh số: field vắng mặt coi như 0 để $gt/$lt hoạt động đúng.
            elif op in ("$gt", "$gte", "$lt", "$lte"):
                if actual is None:
                    if op in ("$gt", "$gte"):
                        left: Any = 0
                    else:
                        return False
                else:
                    left = actual
                try:
                    if op == "$gt":
                        if not left > operand:
                            return False
                    elif op == "$gte":
                        if not left >= operand:
                            return False
                    elif op == "$lt":
                        if not left < operand:
                            return False
                    else:
                        if not left <= operand:
                            return False
                except TypeError:
                    return False
            else:
                raise ValueError(f"Toán tử không được hỗ trợ: {op}")
        return True

    @classmethod
    def _match(cls, doc: dict[str, Any], query: dict[str, Any]) -> bool:
        for key, expected in query.items():
            if not cls._match_operators(_get_path(doc, key), expected):
                return False
        return True

    async def _find(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        async with self._lock:
            return [dict(doc) for doc in self._data if self._match(doc, query)]

    async def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        async with self._lock:
            for doc in self._data:
                if self._match(doc, query):
                    return dict(doc)
        return None

    def find(self, query: dict[str, Any]) -> JsonCursor:
        return JsonCursor(self, query)

    async def count_documents(self, query: dict[str, Any]) -> int:
        async with self._lock:
            return sum(1 for doc in self._data if self._match(doc, query))

    # ----- Ghi -----
    async def insert_one(self, doc: dict[str, Any]) -> _InsertResult:
        async with self._lock:
            self._data.append(dict(doc))
            self._save()
        return _InsertResult(doc.get("_id"))

    async def update_one(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
        upsert: bool = False,
    ) -> _WriteResult:
        async with self._lock:
            for doc in self._data:
                if self._match(doc, query):
                    self._apply_set(doc, update.get("$set", {}))
                    self._save()
                    return _WriteResult(matched=1, modified=1)
            if upsert:
                new_doc: dict[str, Any] = dict(query)
                new_doc.update(update.get("$set", {}))
                self._data.append(new_doc)
                self._save()
                return _WriteResult(upserted=new_doc.get("_id"))
        return _WriteResult()

    async def delete_one(self, query: dict[str, Any]) -> _DeleteResult:
        async with self._lock:
            for i, doc in enumerate(self._data):
                if self._match(doc, query):
                    del self._data[i]
                    self._save()
                    return _DeleteResult(deleted=1)
        return _DeleteResult()

    async def delete_many(self, query: dict[str, Any]) -> _DeleteResult:
        async with self._lock:
            before = len(self._data)
            self._data = [doc for doc in self._data if not self._match(doc, query)]
            deleted = before - len(self._data)
            if deleted:
                self._save()
            return _DeleteResult(deleted=deleted)

    async def find_one_and_delete(self, query: dict[str, Any]) -> dict[str, Any] | None:
        async with self._lock:
            for i, doc in enumerate(self._data):
                if self._match(doc, query):
                    removed = self._data.pop(i)
                    self._save()
                    return removed
        return None

    @staticmethod
    def _apply_set(doc: dict[str, Any], updates: dict[str, Any]) -> None:
        for key, value in updates.items():
            _set_path(doc, key, value)


# ---------------------------------------------------------------
# Store & entry point
# ---------------------------------------------------------------

class JsonStore:
    """Bao quanh data/ — truy cập collection qua store['tên_collection']."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self._collections: dict[str, JsonCollection] = {}

    def __getitem__(self, name: str) -> JsonCollection:
        if name not in self._collections:
            self._collections[name] = JsonCollection(self.data_dir / f"{name}.json")
        return self._collections[name]


class Database:
    """Quản lý JSON storage dùng chung cho toàn bot (singleton)."""

    _store: JsonStore | None = None

    @classmethod
    async def connect(cls) -> JsonStore:
        """Mở storage (tạo thư mục data/ nếu chưa có)."""
        if cls._store is None:
            cfg = load_config()
            cfg.data_dir.mkdir(parents=True, exist_ok=True)
            cls._store = JsonStore(cfg.data_dir)
        return cls._store

    @classmethod
    def get_db(cls) -> JsonStore:
        """Lấy store instance (phải gọi connect trước)."""
        if cls._store is None:
            raise RuntimeError("Database chưa được kết nối. Gọi Database.connect() trước.")
        return cls._store

    @classmethod
    async def close(cls) -> None:
        """Đóng storage (không mất dữ liệu — mọi thay đổi đã ghi file)."""
        cls._store = None
