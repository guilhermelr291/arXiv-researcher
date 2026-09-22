"""Apply a ready compaction cut, watermark bounds, and late job results."""

from __future__ import annotations

import asyncio
import unittest

import tiktoken
from langgraph.graph.message import RemoveMessage, add_messages

from plan_based_researcher.agents.summarizer import SummaryResult
from plan_based_researcher.compaction import (
    plan_compact,
    select_watermark,
    thread_token_count,
)
from plan_based_researcher.policy import Policy
from plan_based_researcher.repo.compaction import CompactionRow
from tests.compaction_memory import MemoryCompactionStore


class _Clock:
    def __init__(self, t: float = 10_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


class _Hold:
    def __init__(self, result: SummaryResult | None = None, error: BaseException | None = None) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self._result = result or SummaryResult(text="DONE", input_tokens=1, output_tokens=1)
        self._error = error

    async def summarize(self, prompt: str) -> SummaryResult:
        self.started.set()
        await self.release.wait()
        if self._error is not None:
            raise self._error
        return self._result


def _msg(mid: str, role: str, tokens: int, content: str | None = None) -> dict:
    return {
        "id": mid,
        "role": role,
        "content": content if content is not None else mid,
        "token_count": tokens,
    }


def _ids(messages: list) -> list[str]:
    found = []
    for message in messages:
        if isinstance(message, dict):
            found.append(str(message.get("id") or ""))
        else:
            found.append(str(getattr(message, "id", "") or ""))
    return found


class CompactionApplyTest(unittest.IsolatedAsyncioTestCase):
    def _cut_messages(self) -> list[dict]:
        return [
            _msg("m1", "user", 1),
            _msg("m2", "assistant", 1),
            _msg("m3", "user", 47999),
        ]

    async def _ready(self, *, watermark: str = "m2", base: str = "", summary: str = "STORED-SUMMARY") -> tuple:
        store = MemoryCompactionStore()
        await store.upsert(
            CompactionRow(
                thread_id="t-1",
                status="ready",
                watermark=watermark,
                base_watermark=base,
                summary=summary,
            )
        )
        return store

    async def test_ready_over_48000_removes_through_watermark(self) -> None:
        messages = self._cut_messages()
        store = await self._ready()
        state = {
            "messages": messages,
            "conversation_summary": "KEEP",
            "applied_watermark": "",
        }
        result = await plan_compact(state, store, thread_id="t-1", now=_Clock())
        self.assertEqual(_ids(result.update["messages"]), ["m1", "m2"])
        self.assertEqual(result.update["conversation_summary"], "STORED-SUMMARY")
        merged = add_messages(messages, result.update["messages"])
        self.assertEqual(_ids(merged), ["m3"])

    async def test_applied_status_and_state_watermark_after_cut(self) -> None:
        store = await self._ready()
        result = await plan_compact(
            {
                "messages": self._cut_messages(),
                "conversation_summary": "",
                "applied_watermark": "",
            },
            store,
            thread_id="t-1",
            now=_Clock(),
        )
        row = await store.get("t-1")
        assert row is not None
        self.assertEqual(row.status, "applied")
        self.assertEqual(result.update["applied_watermark"], "m2")

    async def test_message_after_watermark_remains(self) -> None:
        messages = self._cut_messages()
        store = await self._ready()
        result = await plan_compact(
            {"messages": messages, "conversation_summary": "", "applied_watermark": ""},
            store,
            thread_id="t-1",
            now=_Clock(),
        )
        merged = add_messages(messages, result.update["messages"])
        self.assertIn("m3", _ids(merged))

    async def test_ready_at_or_under_48000_does_not_remove(self) -> None:
        for total in (0, 48000):
            with self.subTest(total=total):
                if total == 0:
                    messages = [_msg("m1", "user", 0), _msg("m2", "assistant", 0)]
                else:
                    messages = [_msg("m1", "user", 16000), _msg("m2", "assistant", 32000)]
                store = await self._ready()
                before = _ids(messages)
                result = await plan_compact(
                    {
                        "messages": messages,
                        "conversation_summary": "",
                        "applied_watermark": "",
                    },
                    store,
                    thread_id="t-1",
                    now=_Clock(),
                )
                self.assertNotIn("messages", result.update)
                row = await store.get("t-1")
                assert row is not None
                self.assertEqual(row.status, "ready")
                self.assertEqual(_ids(messages), before)

    async def test_missing_watermark_is_discarded(self) -> None:
        messages = [_msg("m1", "user", 50000)]
        store = await self._ready(watermark="missing", summary="ROW")
        state = {
            "messages": messages,
            "conversation_summary": "KEEP",
            "applied_watermark": "",
        }
        result = await plan_compact(state, store, thread_id="t-1", now=_Clock())
        row = await store.get("t-1")
        assert row is not None
        self.assertEqual(row.status, "discarded")
        self.assertEqual(_ids(messages), ["m1"])
        self.assertNotIn("messages", result.update)
        self.assertEqual(state["conversation_summary"], "KEEP")

    async def test_base_watermark_mismatch_is_discarded(self) -> None:
        messages = self._cut_messages()
        store = await self._ready(base="old-mark")
        state = {
            "messages": messages,
            "conversation_summary": "KEEP",
            "applied_watermark": "other-mark",
        }
        result = await plan_compact(state, store, thread_id="t-1", now=_Clock())
        row = await store.get("t-1")
        assert row is not None
        self.assertEqual(row.status, "discarded")
        self.assertEqual(_ids(messages), ["m1", "m2", "m3"])
        self.assertNotIn("messages", result.update)
        self.assertEqual(state["conversation_summary"], "KEEP")

    async def test_already_applied_watermark_does_not_remove(self) -> None:
        messages = self._cut_messages()
        store = await self._ready()
        result = await plan_compact(
            {
                "messages": messages,
                "conversation_summary": "KEEP",
                "applied_watermark": "m2",
            },
            store,
            thread_id="t-1",
            now=_Clock(),
        )
        row = await store.get("t-1")
        assert row is not None
        self.assertEqual(row.status, "applied")
        self.assertNotIn("messages", result.update)
        self.assertIn("m1", _ids(messages))

    def test_watermark_keeps_16000_tokens_from_a_user_message(self) -> None:
        messages = [
            _msg("pre", "user", 100),
            _msg("wm", "assistant", 100),
            _msg("suf", "user", 16000),
        ]
        choice = select_watermark(messages)
        assert choice is not None
        self.assertEqual(choice.suffix_tokens, 16000)
        self.assertEqual(messages[choice.suffix_index]["role"], "user")
        self.assertEqual(choice.watermark_id, "wm")
        self.assertEqual(messages[choice.suffix_index - 1]["id"], choice.watermark_id)

    def test_watermark_extends_suffix_to_a_user_message(self) -> None:
        messages = [
            _msg("p", "assistant", 100),
            _msg("u", "user", 100),
            _msg("a", "assistant", 16000),
        ]
        choice = select_watermark(messages)
        assert choice is not None
        self.assertEqual(messages[choice.suffix_index]["role"], "user")
        self.assertGreater(choice.suffix_tokens, 16000)

    async def test_short_prefix_or_no_user_boundary_does_not_cut(self) -> None:
        cases = {
            "prefix-7999": [
                _msg("p", "assistant", 7999),
                _msg("u", "user", 40002),
            ],
            "no-user": [
                _msg("a", "assistant", 24000),
                _msg("b", "assistant", 24001),
            ],
        }
        for name, messages in cases.items():
            with self.subTest(name=name):
                store = MemoryCompactionStore()
                before = len(messages)
                result = await plan_compact(
                    {
                        "messages": messages,
                        "conversation_summary": "",
                        "applied_watermark": "",
                    },
                    store,
                    thread_id="t-1",
                    summarizer=_Hold(),
                    now=_Clock(),
                )
                row = await store.get("t-1")
                self.assertTrue(row is None or row.status != "running")
                merged = add_messages(messages, result.update.get("messages") or [])
                self.assertEqual(len(merged), before)
                if result.job is not None:
                    result.job.cancel()

    def test_token_count_uses_o200k_base_and_omits_system_and_papers(self) -> None:
        summary = "summarize the LoRA paper"
        user = "evidence about rank"
        system = "SYSTEM-SECRET-SHOULD-NOT-COUNT"
        paper = "PAPER-SECRET-SHOULD-NOT-COUNT"
        state = {
            "conversation_summary": summary,
            "papers": [{"title": paper, "arxiv_id": "2401.00001"}],
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        enc = tiktoken.get_encoding("o200k_base")
        expected = len(enc.encode(summary)) + len(enc.encode(user))
        self.assertEqual(thread_token_count(state), expected)
        cl100k = tiktoken.get_encoding("cl100k_base")
        self.assertNotEqual(enc.encode(summary), cl100k.encode(summary))
        self.assertEqual(Policy.chunk_encoding, "cl100k_base")
        inflated = expected + len(enc.encode(system)) + len(enc.encode(paper))
        self.assertNotEqual(thread_token_count(state), inflated)

    def test_stored_message_token_count_is_reused(self) -> None:
        text = "hello world this is definitely more than one token"
        enc = tiktoken.get_encoding("o200k_base")
        self.assertNotEqual(len(enc.encode(text)), 100)
        state = {
            "conversation_summary": "",
            "messages": [{"role": "user", "content": text, "token_count": 100}],
        }
        self.assertEqual(thread_token_count(state), 100)

    async def test_remove_message_ids_applied_by_add_messages(self) -> None:
        messages = self._cut_messages()
        store = await self._ready()
        result = await plan_compact(
            {"messages": messages, "conversation_summary": "", "applied_watermark": ""},
            store,
            thread_id="t-1",
            now=_Clock(),
        )
        removals = result.update["messages"]
        self.assertEqual(len(removals), 2)
        for message, mid in zip(removals, ("m1", "m2"), strict=True):
            self.assertIsInstance(message, RemoveMessage)
            self.assertEqual(message.id, mid)
        merged = add_messages(messages, removals)
        self.assertEqual(_ids(merged), ["m3"])

    async def test_omitted_checkpoint_fields_mean_no_summary(self) -> None:
        messages = [_msg("m1", "user", 10), _msg("m2", "assistant", 10)]
        state = {"messages": messages, "outcome": "pending"}
        store = MemoryCompactionStore()
        result = await plan_compact(state, store, thread_id="t-1", now=_Clock())
        self.assertNotIn("messages", result.update)
        self.assertEqual(_ids(messages), ["m1", "m2"])
        self.assertEqual(store.rows, {})

    async def test_stale_running_fails_and_cooldown_is_30_seconds(self) -> None:
        messages = [
            _msg("wm-1", "assistant", 8000),
            _msg("keep", "user", 40001),
        ]
        state = {
            "messages": messages,
            "conversation_summary": "",
            "applied_watermark": "",
            "outcome": "pending",
        }
        clock = _Clock(t=1_000.0)
        store = MemoryCompactionStore()
        await store.upsert(
            CompactionRow(
                thread_id="t-1",
                status="running",
                watermark="wm-0",
                summary="OLD-SUMMARY",
                running_started_at=clock.t - 90,
            )
        )
        await plan_compact(state, store, thread_id="t-1", now=clock)
        stayed = await store.get("t-1")
        assert stayed is not None
        self.assertEqual(stayed.status, "running")

        store = MemoryCompactionStore()
        await store.upsert(
            CompactionRow(
                thread_id="t-1",
                status="running",
                watermark="wm-0",
                summary="OLD-SUMMARY",
                running_started_at=clock.t - 91,
            )
        )
        await plan_compact(state, store, thread_id="t-1", now=clock)
        failed = await store.get("t-1")
        assert failed is not None
        self.assertEqual(failed.status, "failed")
        failed_at = float(failed.failed_at or 0)

        clock.t = failed_at + 29
        hold = _Hold()
        early = await plan_compact(
            state, store, thread_id="t-1", summarizer=hold, now=clock
        )
        row = await store.get("t-1")
        assert row is not None
        self.assertEqual(row.status, "failed")
        self.assertIsNone(early.job)

        clock.t = failed_at + 30
        hold = _Hold()
        started = await plan_compact(
            state, store, thread_id="t-1", summarizer=hold, now=clock
        )
        await hold.started.wait()
        row = await store.get("t-1")
        assert row is not None
        self.assertEqual(row.status, "running")
        started.job.cancel()
        try:
            await started.job
        except asyncio.CancelledError:
            pass

    async def test_summarizer_ready_after_turn_returns(self) -> None:
        messages = [
            _msg("wm-1", "assistant", 8000),
            _msg("keep", "user", 40001),
        ]
        state = {
            "messages": messages,
            "conversation_summary": "",
            "applied_watermark": "",
            "outcome": "pending",
        }
        store = MemoryCompactionStore()
        hold = _Hold(SummaryResult(text="DONE", input_tokens=2, output_tokens=2))
        result = await plan_compact(
            state, store, thread_id="t-1", summarizer=hold, now=_Clock()
        )
        await hold.started.wait()
        row = await store.get("t-1")
        assert row is not None
        self.assertEqual(row.status, "running")
        self.assertEqual(state["outcome"], "pending")
        self.assertNotIn("outcome", result.update)
        hold.release.set()
        assert result.job is not None
        await result.job
        row = await store.get("t-1")
        assert row is not None
        self.assertEqual(row.status, "ready")
        self.assertEqual(state["outcome"], "pending")

    async def test_summarizer_failure_after_turn_keeps_outcome_pending(self) -> None:
        messages = [
            _msg("wm-1", "assistant", 8000),
            _msg("keep", "user", 40001),
        ]
        state = {
            "messages": messages,
            "conversation_summary": "",
            "applied_watermark": "",
            "outcome": "pending",
        }
        store = MemoryCompactionStore()
        await store.upsert(
            CompactionRow(thread_id="t-1", status="applied", summary="OLD-SUMMARY")
        )
        hold = _Hold(error=RuntimeError("boom"))
        result = await plan_compact(
            state, store, thread_id="t-1", summarizer=hold, now=_Clock()
        )
        await hold.started.wait()
        self.assertEqual(state["outcome"], "pending")
        hold.release.set()
        assert result.job is not None
        await result.job
        row = await store.get("t-1")
        assert row is not None
        self.assertEqual(row.status, "failed")
        self.assertEqual(row.summary, "OLD-SUMMARY")
        self.assertEqual(state["outcome"], "pending")

    async def test_late_success_does_not_replace_a_newer_watermark(self) -> None:
        messages = [
            _msg("wm-1", "assistant", 8000),
            _msg("keep", "user", 40001),
        ]
        state = {
            "messages": messages,
            "conversation_summary": "",
            "applied_watermark": "",
            "outcome": "pending",
        }
        store = MemoryCompactionStore()
        hold = _Hold(SummaryResult(text="OLD-JOB", input_tokens=1, output_tokens=1))
        result = await plan_compact(
            state, store, thread_id="t-1", summarizer=hold, now=_Clock()
        )
        await hold.started.wait()
        await store.upsert(
            CompactionRow(
                thread_id="t-1",
                status="running",
                watermark="wm-2",
                summary="NEWER",
                running_started_at=1.0,
            )
        )
        hold.release.set()
        assert result.job is not None
        await result.job
        row = await store.get("t-1")
        assert row is not None
        self.assertEqual(row.status, "running")
        self.assertEqual(row.watermark, "wm-2")
        self.assertEqual(row.summary, "NEWER")

    async def test_late_failure_does_not_fail_a_newer_watermark(self) -> None:
        messages = [
            _msg("wm-1", "assistant", 8000),
            _msg("keep", "user", 40001),
        ]
        state = {
            "messages": messages,
            "conversation_summary": "",
            "applied_watermark": "",
            "outcome": "pending",
        }
        store = MemoryCompactionStore()
        hold = _Hold(error=RuntimeError("boom"))
        result = await plan_compact(
            state, store, thread_id="t-1", summarizer=hold, now=_Clock()
        )
        await hold.started.wait()
        await store.upsert(
            CompactionRow(
                thread_id="t-1",
                status="running",
                watermark="wm-2",
                summary="NEWER",
            )
        )
        hold.release.set()
        assert result.job is not None
        await result.job
        row = await store.get("t-1")
        assert row is not None
        self.assertEqual(row.status, "running")
        self.assertEqual(row.watermark, "wm-2")
        self.assertEqual(row.summary, "NEWER")
        self.assertEqual(row.error, "")


if __name__ == "__main__":
    unittest.main()
