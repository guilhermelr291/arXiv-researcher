"""Transcript store schema, kinds, JSON keys, and item identity."""

from __future__ import annotations

import inspect
import unittest

from plan_based_researcher.main import lifespan
from plan_based_researcher.repo.transcript import PgTranscriptStore, TRANSCRIPT_SCHEMA_SQL

from tests.transcript_memory import MemoryTranscriptStore

_ASSISTANT_KEYS = ("outcome", "content", "gate", "plan", "steps", "citations")
_GATE_KEYS = ("in_domain", "reason")
_PLAN_KEYS = ("index", "agent", "task", "status", "feedback")
_STEPS_KEYS = ("count", "elapsed_ms", "nodes")
_NODE_KEYS = ("name", "query_used")
_CITATION_KEYS = (
    "n",
    "chunk_id",
    "arxiv_id",
    "title",
    "year",
    "url",
    "excerpt",
)


def _assistant_payload() -> dict:
    return {
        "outcome": "done",
        "content": "answer [1]",
        "gate": {"in_domain": True, "reason": "in scope"},
        "plan": [
            {
                "index": 0,
                "agent": "search",
                "task": "Find LoRA papers",
                "status": "passed",
                "feedback": "ok",
            }
        ],
        "steps": {
            "count": 1,
            "elapsed_ms": 40,
            "nodes": [{"name": "search", "query_used": "LoRA"}],
        },
        "citations": [
            {
                "n": 1,
                "chunk_id": "c1",
                "arxiv_id": "2401.00001",
                "title": "LoRA",
                "year": 2024,
                "url": "https://arxiv.org/abs/2401.00001",
                "excerpt": "low-rank",
            }
        ],
    }


class TranscriptStoreTest(unittest.IsolatedAsyncioTestCase):
    def test_schema_sql_create_if_not_exists_without_drop(self) -> None:
        sql = TRANSCRIPT_SCHEMA_SQL
        self.assertIn("CREATE TABLE IF NOT EXISTS threads", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS transcript_items", sql)
        self.assertNotIn("DROP", sql)

    def test_lifespan_calls_transcript_ensure_schema(self) -> None:
        text = inspect.getsource(lifespan)
        self.assertIn("PgTranscriptStore", text)
        self.assertIn("await transcript.ensure_schema()", text)

    def test_insert_wraps_thread_and_item_in_one_transaction(self) -> None:
        text = inspect.getsource(PgTranscriptStore.insert)
        self.assertIn("conn.transaction()", text)

    async def test_insert_stores_thread_id(self) -> None:
        store = MemoryTranscriptStore()
        await store.insert_user("tid-1", "u1", "What is LoRA?")
        self.assertIn("tid-1", store.threads)
        self.assertEqual(store.threads["tid-1"].thread_id, "tid-1")
        self.assertEqual(store.items[0].thread_id, "tid-1")

    async def test_kinds_user_assistant_turn_reject_tool_call(self) -> None:
        store = MemoryTranscriptStore()
        cases = (
            ("user", {"content": "hello"}, 1),
            ("assistant_turn", _assistant_payload(), 2),
            ("tool_call", {"name": "search"}, 2),
        )
        for kind, payload, expected_count in cases:
            with self.subTest(kind=kind):
                await store.insert("tid-k", f"id-{kind}", kind, payload)
                self.assertEqual(len(store.items), expected_count)
                if kind != "tool_call":
                    self.assertEqual(store.items[-1].kind, kind)
                else:
                    self.assertFalse(any(item.kind == "tool_call" for item in store.items))

    async def test_assistant_turn_json_key_set(self) -> None:
        store = MemoryTranscriptStore()
        await store.insert_assistant_turn("tid-1", "a1", _assistant_payload())
        payload = store.items[0].payload
        for key in _ASSISTANT_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, payload)
        for key in _GATE_KEYS:
            with self.subTest(gate=key):
                self.assertIn(key, payload["gate"])
        for key in _PLAN_KEYS:
            with self.subTest(plan=key):
                self.assertIn(key, payload["plan"][0])
        for key in _STEPS_KEYS:
            with self.subTest(steps=key):
                self.assertIn(key, payload["steps"])
        for key in _NODE_KEYS:
            with self.subTest(node=key):
                self.assertIn(key, payload["steps"]["nodes"][0])
        for key in _CITATION_KEYS:
            with self.subTest(citation=key):
                self.assertIn(key, payload["citations"][0])

    async def test_repeat_id_leaves_one_row(self) -> None:
        store = MemoryTranscriptStore()
        await store.insert_user("tid-1", "u1", "first")
        await store.insert_user("tid-1", "u1", "duplicate")
        matching = [item for item in store.items if item.id == "u1"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].payload["content"], "first")
