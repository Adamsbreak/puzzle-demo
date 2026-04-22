from __future__ import annotations

import copy
import json
import logging
import os
import sqlite3
import time
import uuid
from pathlib import Path
from threading import RLock
from typing import Any


LOGGER = logging.getLogger(__name__)

_PLACEHOLDER_TITLES = {"", "new chat", "untitled"}
_DEFAULT_SUMMARY = {"text": "", "suggestions": []}


class PersistentSessionStore:
    def __init__(self) -> None:
        backend = (os.getenv("PUZZLE_AI_SESSION_STORE") or "sqlite").strip().lower()
        self._backend = backend if backend in {"sqlite", "mysql"} else "sqlite"
        default_path = Path(__file__).resolve().parents[1] / "data" / "ai_sessions.sqlite3"
        self._sqlite_path = Path(os.getenv("PUZZLE_AI_SESSION_DB_PATH") or default_path)
        self._mysql_host = os.getenv("PUZZLE_AI_SESSION_MYSQL_HOST", "127.0.0.1")
        self._mysql_port = int(os.getenv("PUZZLE_AI_SESSION_MYSQL_PORT", "3306"))
        self._mysql_user = os.getenv("PUZZLE_AI_SESSION_MYSQL_USER", "root")
        self._mysql_password = os.getenv("PUZZLE_AI_SESSION_MYSQL_PASSWORD", "")
        self._mysql_database = os.getenv("PUZZLE_AI_SESSION_MYSQL_DATABASE", "puzzle_ai")
        # Re-entrant because save_context() may need to read the existing
        # session record while already holding the store lock.
        self._lock = RLock()
        self._initialized = False
        self._ensure_initialized()

    def backend_name(self) -> str:
        return self._backend

    def describe(self) -> dict[str, str]:
        if self._backend == "mysql":
            return {
                "backend": "mysql",
                "database": self._mysql_database,
                "host": self._mysql_host,
                "port": str(self._mysql_port),
            }
        return {
            "backend": "sqlite",
            "path": str(self._sqlite_path),
        }

    def _new_context(self, initial_level: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "title": "New chat",
            "messages": [],
            "working_level": copy.deepcopy(initial_level or {}),
            "analysis_summary": copy.deepcopy(_DEFAULT_SUMMARY),
            "last_intent": {},
            "suggestions": [],
        }

    def list_sessions(self, user_id: str) -> list[dict[str, Any]]:
        self._ensure_initialized()
        if self._backend == "mysql":
            rows = self._list_mysql_rows(user_id)
        else:
            rows = self._list_sqlite_rows(user_id)
        return [self._summary_from_row(row) for row in rows]

    def get_session(
        self,
        user_id: str,
        session_id: str,
        initial_level: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        self._ensure_initialized()
        row = self._fetch_row(user_id, session_id)
        if row is None:
            return None
        detail = self._detail_from_row(row)
        if initial_level and not detail.get("working_level"):
            detail["working_level"] = copy.deepcopy(initial_level)
        return detail

    def create_session(
        self,
        user_id: str,
        initial_level: dict[str, Any] | None = None,
        title: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_initialized()
        actual_session_id = str(session_id or ("session-" + uuid.uuid4().hex[:12]))
        with self._lock:
            context = self._new_context(initial_level)
            if title and title.strip():
                context["title"] = title.strip()
            record = self._build_record(user_id, actual_session_id, context, existing=None)
            self._upsert_row(record)
        detail = self.get_session(user_id, actual_session_id, initial_level)
        if detail is None:
            raise RuntimeError("Failed to create session.")
        return detail

    def get_context(self, user_id: str, session_id: str, initial_level: dict[str, Any]) -> dict[str, Any]:
        detail = self.get_session(user_id, session_id, initial_level)
        if detail is None:
            detail = self.create_session(user_id, initial_level=initial_level, session_id=session_id)
        return {
            "title": str(detail.get("title") or "New chat"),
            "messages": copy.deepcopy(detail.get("messages") or []),
            "working_level": copy.deepcopy(detail.get("working_level") or initial_level or {}),
            "analysis_summary": copy.deepcopy(detail.get("analysis_summary") or _DEFAULT_SUMMARY),
            "last_intent": copy.deepcopy(detail.get("last_intent") or {}),
            "suggestions": list(detail.get("suggestions") or []),
        }

    def save_context(self, user_id: str, session_id: str, context: dict[str, Any]) -> None:
        self._ensure_initialized()
        with self._lock:
            existing = self.get_session(user_id, session_id, context.get("working_level"))
            record = self._build_record(user_id, session_id, context, existing=existing)
            self._upsert_row(record)

    def _ensure_initialized(self) -> None:
        with self._lock:
            if self._initialized:
                return
            if self._backend == "mysql":
                self._initialize_mysql()
            else:
                self._initialize_sqlite()
            self._initialized = True

    def _initialize_sqlite(self) -> None:
        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect_sqlite()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_sessions (
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    preview TEXT NOT NULL,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    messages_json TEXT NOT NULL,
                    working_level_json TEXT NOT NULL,
                    analysis_summary_json TEXT NOT NULL,
                    last_intent_json TEXT NOT NULL,
                    suggestions_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (user_id, session_id)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_sessions_user_updated ON ai_sessions (user_id, updated_at)"
            )
            connection.commit()
        finally:
            connection.close()

    def _initialize_mysql(self) -> None:
        connection = self._connect_mysql()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_sessions (
                    user_id VARCHAR(190) NOT NULL,
                    session_id VARCHAR(190) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    preview TEXT NOT NULL,
                    message_count INT NOT NULL DEFAULT 0,
                    messages_json LONGTEXT NOT NULL,
                    working_level_json LONGTEXT NOT NULL,
                    analysis_summary_json LONGTEXT NOT NULL,
                    last_intent_json LONGTEXT NOT NULL,
                    suggestions_json LONGTEXT NOT NULL,
                    created_at DOUBLE NOT NULL,
                    updated_at DOUBLE NOT NULL,
                    PRIMARY KEY (user_id, session_id),
                    KEY idx_ai_sessions_user_updated (user_id, updated_at)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            connection.commit()
        finally:
            connection.close()

    def _connect_sqlite(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._sqlite_path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _connect_mysql(self) -> Any:
        try:
            import pymysql
        except ImportError as error:  # pragma: no cover - depends on runtime env
            raise RuntimeError(
                "PyMySQL is required for PUZZLE_AI_SESSION_STORE=mysql. Install backend requirements first."
            ) from error

        return pymysql.connect(
            host=self._mysql_host,
            port=self._mysql_port,
            user=self._mysql_user,
            password=self._mysql_password,
            database=self._mysql_database,
            charset="utf8mb4",
            autocommit=False,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def _list_sqlite_rows(self, user_id: str) -> list[sqlite3.Row]:
        connection = self._connect_sqlite()
        try:
            cursor = connection.execute(
                """
                SELECT user_id, session_id, title, preview, message_count, suggestions_json, created_at, updated_at
                FROM ai_sessions
                WHERE user_id = ?
                ORDER BY updated_at DESC, created_at DESC
                """,
                (user_id,),
            )
            return cursor.fetchall()
        finally:
            connection.close()

    def _list_mysql_rows(self, user_id: str) -> list[dict[str, Any]]:
        connection = self._connect_mysql()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT user_id, session_id, title, preview, message_count, suggestions_json, created_at, updated_at
                FROM ai_sessions
                WHERE user_id = %s
                ORDER BY updated_at DESC, created_at DESC
                """,
                (user_id,),
            )
            return list(cursor.fetchall())
        finally:
            connection.close()

    def _fetch_row(self, user_id: str, session_id: str) -> Any | None:
        if self._backend == "mysql":
            connection = self._connect_mysql()
            try:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    SELECT user_id, session_id, title, preview, message_count, messages_json, working_level_json,
                           analysis_summary_json, last_intent_json, suggestions_json, created_at, updated_at
                    FROM ai_sessions
                    WHERE user_id = %s AND session_id = %s
                    """,
                    (user_id, session_id),
                )
                return cursor.fetchone()
            finally:
                connection.close()

        connection = self._connect_sqlite()
        try:
            cursor = connection.execute(
                """
                SELECT user_id, session_id, title, preview, message_count, messages_json, working_level_json,
                       analysis_summary_json, last_intent_json, suggestions_json, created_at, updated_at
                FROM ai_sessions
                WHERE user_id = ? AND session_id = ?
                """,
                (user_id, session_id),
            )
            return cursor.fetchone()
        finally:
            connection.close()

    def _upsert_row(self, record: dict[str, Any]) -> None:
        if self._backend == "mysql":
            self._upsert_mysql_row(record)
            return
        self._upsert_sqlite_row(record)

    def _upsert_sqlite_row(self, record: dict[str, Any]) -> None:
        connection = self._connect_sqlite()
        try:
            connection.execute(
                """
                INSERT INTO ai_sessions (
                    user_id, session_id, title, preview, message_count, messages_json, working_level_json,
                    analysis_summary_json, last_intent_json, suggestions_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, session_id) DO UPDATE SET
                    title = excluded.title,
                    preview = excluded.preview,
                    message_count = excluded.message_count,
                    messages_json = excluded.messages_json,
                    working_level_json = excluded.working_level_json,
                    analysis_summary_json = excluded.analysis_summary_json,
                    last_intent_json = excluded.last_intent_json,
                    suggestions_json = excluded.suggestions_json,
                    updated_at = excluded.updated_at
                """,
                (
                    record["user_id"],
                    record["session_id"],
                    record["title"],
                    record["preview"],
                    record["message_count"],
                    record["messages_json"],
                    record["working_level_json"],
                    record["analysis_summary_json"],
                    record["last_intent_json"],
                    record["suggestions_json"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def _upsert_mysql_row(self, record: dict[str, Any]) -> None:
        connection = self._connect_mysql()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO ai_sessions (
                    user_id, session_id, title, preview, message_count, messages_json, working_level_json,
                    analysis_summary_json, last_intent_json, suggestions_json, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    title = VALUES(title),
                    preview = VALUES(preview),
                    message_count = VALUES(message_count),
                    messages_json = VALUES(messages_json),
                    working_level_json = VALUES(working_level_json),
                    analysis_summary_json = VALUES(analysis_summary_json),
                    last_intent_json = VALUES(last_intent_json),
                    suggestions_json = VALUES(suggestions_json),
                    updated_at = VALUES(updated_at)
                """,
                (
                    record["user_id"],
                    record["session_id"],
                    record["title"],
                    record["preview"],
                    record["message_count"],
                    record["messages_json"],
                    record["working_level_json"],
                    record["analysis_summary_json"],
                    record["last_intent_json"],
                    record["suggestions_json"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def _build_record(
        self,
        user_id: str,
        session_id: str,
        context: dict[str, Any],
        existing: dict[str, Any] | None,
    ) -> dict[str, Any]:
        base_context = self._new_context((existing or {}).get("working_level") or context.get("working_level"))
        if existing:
            base_context.update(
                {
                    "title": existing.get("title") or base_context["title"],
                    "messages": copy.deepcopy(existing.get("messages") or []),
                    "working_level": copy.deepcopy(existing.get("working_level") or base_context["working_level"]),
                    "analysis_summary": copy.deepcopy(existing.get("analysis_summary") or _DEFAULT_SUMMARY),
                    "last_intent": copy.deepcopy(existing.get("last_intent") or {}),
                    "suggestions": list(existing.get("suggestions") or []),
                }
            )
        base_context.update(context or {})
        normalized = self._normalize_context(base_context)
        created_at = float((existing or {}).get("created_at") or time.time())
        updated_at = time.time()
        return {
            "user_id": user_id,
            "session_id": session_id,
            "title": normalized["title"],
            "preview": normalized["preview"],
            "message_count": len(normalized["messages"]),
            "messages_json": self._json_dump(normalized["messages"]),
            "working_level_json": self._json_dump(normalized["working_level"]),
            "analysis_summary_json": self._json_dump(normalized["analysis_summary"]),
            "last_intent_json": self._json_dump(normalized["last_intent"]),
            "suggestions_json": self._json_dump(normalized["suggestions"]),
            "created_at": created_at,
            "updated_at": updated_at,
        }

    def _normalize_context(self, context: dict[str, Any]) -> dict[str, Any]:
        messages = self._normalize_messages(context.get("messages"))
        working_level = copy.deepcopy(context.get("working_level") or {})
        analysis_summary = context.get("analysis_summary")
        if not isinstance(analysis_summary, dict):
            analysis_summary = copy.deepcopy(_DEFAULT_SUMMARY)
        else:
            analysis_summary = {
                "text": str(analysis_summary.get("text") or ""),
                "suggestions": self._normalize_suggestions(analysis_summary.get("suggestions")),
            }
        suggestions = self._normalize_suggestions(context.get("suggestions") or analysis_summary.get("suggestions"))
        title = str(context.get("title") or "").strip()
        if title.lower() in _PLACEHOLDER_TITLES:
            title = ""
        if not title:
            title = self._build_title(messages)
        preview = self._build_preview(messages)
        return {
            "title": title,
            "preview": preview,
            "messages": messages,
            "working_level": working_level,
            "analysis_summary": {
                "text": str(analysis_summary.get("text") or ""),
                "suggestions": suggestions,
            },
            "last_intent": copy.deepcopy(context.get("last_intent") or {}),
            "suggestions": suggestions,
        }

    def _normalize_messages(self, messages: Any) -> list[dict[str, str]]:
        output: list[dict[str, str]] = []
        for item in messages or []:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "assistant").strip() or "assistant"
            content = str(item.get("content") or "").strip()
            if role not in {"user", "assistant", "system"} or not content:
                continue
            output.append({"role": role, "content": content})
        return output[-50:]

    def _normalize_suggestions(self, suggestions: Any) -> list[str]:
        output: list[str] = []
        for item in suggestions or []:
            value = str(item or "").strip()
            if not value or value in output:
                continue
            output.append(value)
        return output[:4]

    def _build_title(self, messages: list[dict[str, str]]) -> str:
        for item in messages:
            if item.get("role") == "user":
                return self._truncate(item.get("content", ""), limit=36)
        for item in messages:
            if item.get("content"):
                return self._truncate(item.get("content", ""), limit=36)
        return "New chat"

    def _build_preview(self, messages: list[dict[str, str]]) -> str:
        if not messages:
            return "No messages yet."
        last_message = messages[-1]
        role = "You" if last_message.get("role") == "user" else "AI"
        return self._truncate(f"{role}: {last_message.get('content', '')}", limit=100)

    def _truncate(self, text: str, limit: int) -> str:
        value = reflow_whitespace(text)
        if len(value) <= limit:
            return value
        return value[: max(0, limit - 1)].rstrip() + "..."

    def _summary_from_row(self, row: Any) -> dict[str, Any]:
        return {
            "user_id": str(self._row_value(row, "user_id") or ""),
            "session_id": str(self._row_value(row, "session_id") or ""),
            "title": str(self._row_value(row, "title") or "New chat"),
            "preview": str(self._row_value(row, "preview") or ""),
            "message_count": int(self._row_value(row, "message_count") or 0),
            "suggestions": self._json_load(self._row_value(row, "suggestions_json"), []),
            "created_at": float(self._row_value(row, "created_at") or 0.0),
            "updated_at": float(self._row_value(row, "updated_at") or 0.0),
        }

    def _detail_from_row(self, row: Any) -> dict[str, Any]:
        summary = self._summary_from_row(row)
        return {
            **summary,
            "messages": self._json_load(self._row_value(row, "messages_json"), []),
            "working_level": self._json_load(self._row_value(row, "working_level_json"), {}),
            "analysis_summary": self._json_load(self._row_value(row, "analysis_summary_json"), copy.deepcopy(_DEFAULT_SUMMARY)),
            "last_intent": self._json_load(self._row_value(row, "last_intent_json"), {}),
        }

    def _row_value(self, row: Any, key: str) -> Any:
        if row is None:
            return None
        if isinstance(row, dict):
            return row.get(key)
        return row[key]

    def _json_dump(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def _json_load(self, value: Any, fallback: Any) -> Any:
        if value in (None, ""):
            return copy.deepcopy(fallback)
        try:
            return json.loads(str(value))
        except Exception:
            LOGGER.warning("Failed to decode stored session JSON; using fallback value.")
            return copy.deepcopy(fallback)


def reflow_whitespace(text: str) -> str:
    return " ".join(str(text or "").strip().split())


SESSION_CONTEXT_STORE = PersistentSessionStore()
