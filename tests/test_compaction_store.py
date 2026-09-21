"""Compaction row, schema, and summarizer call."""

from __future__ import annotations

import asyncio
import inspect
import unittest
from unittest.mock import MagicMock, patch

import tiktoken

from plan_based_researcher.agents.registry import PLAN_AGENTS, REGISTRY, planner_prompt_abilities
from plan_based_researcher.agents.summarizer import ConversationSummary, SummarizerRunner
from plan_based_researcher.agents.summarizer import SummaryResult
from plan_based_researcher.compaction import commit_ready, plan_compact
from plan_based_researcher.main import lifespan
from plan_based_researcher.repo.compaction import (
    ALLOWED_STATUS,
    COMPACTION_SCHEMA_SQL,
    CompactionRow,
)
from tests.compaction_memory import MemoryCompactionStore

_SUMMARIZER_LLM = "plan_based_researcher.agents.summarizer.ChatOpenAI"
_HEADINGS = (
    "## Current user goal",
    "## Decisions made (with the reason, when it matters)",
    "## Stated constraints and preferences",
    "## Important entities and values",
    "## What has already been done",
    "## Open items and unanswered questions",
)
_FIELDS = (
    "current_user_goal",
    "decisions_made",
    "constraints_and_preferences",
    "important_entities_and_values",
    "what_has_been_done",
    "open_items",
)


class _Clock:
    def __init__(self, t: float = 10_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


class _SpyTranscript:
    def __init__(self) -> None:
        self.inserts = 0
        self.updates = 0
        self.deletes = 0

    async def insert(self, *args, **kwargs) -> None:
        self.inserts += 1

    async def update(self, *args, **kwargs) -> None:
        self.updates += 1

    async def delete(self, *args, **kwargs) -> None:
        self.deletes += 1


class _RecordingSummarizer:
    def __init__(self, result: SummaryResult | None = None, error: BaseException | None = None) -> None:
        self.prompts: list[str] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self._result = result or SummaryResult(text="x", input_tokens=0, output_tokens=0)
        self._error = error

    async def summarize(self, prompt: str) -> SummaryResult:
        self.prompts.append(prompt)
        self.started.set()
        await self.release.wait()
        if self._error is not None:
            raise self._error
        return self._result


def _over_threshold_messages(watermark: str) -> list[dict]:
    return [
        {"id": watermark, "role": "assistant", "content": "prefix", "token_count": 8000},
        {"id": "keep", "role": "user", "content": "suffix", "token_count": 40001},
    ]


def _state(messages: list[dict], summary: str = "") -> dict:
    return {
        "messages": messages,
        "conversation_summary": summary,
        "applied_watermark": "",
        "outcome": "pending",
    }


async def _cancel(result) -> None:
    if result.job is None:
        return
    result.job.cancel()
    try:
        await result.job
    except asyncio.CancelledError:
        pass


class CompactionStoreTest(unittest.IsolatedAsyncioTestCase):
    def test_schema_is_create_only_and_lifespan_ensures_it(self) -> None:
        sql = COMPACTION_SCHEMA_SQL
        self.assertIn("CREATE TABLE IF NOT EXISTS", sql)
        self.assertIn("thread_id TEXT PRIMARY KEY", sql)
        self.assertNotIn("DROP", sql)
        text = inspect.getsource(lifespan)
        self.assertNotIn("DROP", text)
        self.assertIn("PgCompactionStore", text)
        self.assertIn("await compaction.ensure_schema()", text)

    async def test_second_write_keeps_one_row(self) -> None:
        store = MemoryCompactionStore()
        await commit_ready(store, "t-1", summary="FIRST", watermark="w")
        await commit_ready(store, "t-1", summary="NEW-SUMMARY", watermark="w")
        self.assertEqual(len(store.rows), 1)
        self.assertEqual(store.rows["t-1"].summary, "NEW-SUMMARY")

    async def test_status_set_rejects_paused(self) -> None:
        store = MemoryCompactionStore()
        for status in ("running", "ready", "applied", "failed", "discarded"):
            with self.subTest(status=status):
                await store.upsert(CompactionRow(thread_id="t-status", status=status))
                stored = await store.get("t-status")
                self.assertIsNotNone(stored)
                assert stored is not None
                self.assertEqual(stored.status, status)
        sql = COMPACTION_SCHEMA_SQL
        for status in ALLOWED_STATUS:
            self.assertIn(f"'{status}'", sql)
        with self.assertRaises(ValueError):
            await store.upsert(CompactionRow(thread_id="t-paused", status="paused"))
        self.assertIsNone(await store.get("t-paused"))

    async def test_job_start_refusals(self) -> None:
        clock = _Clock()
        messages = _over_threshold_messages("wm-1")
        cases = {
            "tokens-48000": {
                "row": CompactionRow(thread_id="t-1", status="applied", summary="OLD"),
                "messages": [
                    {"id": "wm-1", "role": "assistant", "content": "p", "token_count": 8000},
                    {"id": "keep", "role": "user", "content": "s", "token_count": 40000},
                ],
                "expect": "applied",
            },
            "failed-29s": {
                "row": CompactionRow(
                    thread_id="t-1",
                    status="failed",
                    summary="OLD",
                    watermark="wm-0",
                    failed_at=clock.t - 29,
                ),
                "messages": messages,
                "expect": "failed",
            },
            "running": {
                "row": CompactionRow(
                    thread_id="t-1",
                    status="running",
                    summary="OLD",
                    watermark="wm-0",
                    running_started_at=clock.t,
                ),
                "messages": messages,
                "expect": "running",
            },
            "ready": {
                "row": CompactionRow(
                    thread_id="t-1",
                    status="ready",
                    summary="OLD",
                    watermark="absent-from-messages",
                    base_watermark="",
                ),
                "messages": messages,
                "expect": "discarded",
            },
        }
        for name, case in cases.items():
            with self.subTest(name=name):
                store = MemoryCompactionStore()
                await store.upsert(case["row"])
                result = await plan_compact(
                    _state(case["messages"]),
                    store,
                    thread_id="t-1",
                    summarizer=_RecordingSummarizer(),
                    now=clock,
                )
                row = await store.get("t-1")
                assert row is not None
                self.assertNotEqual(row.status, "running") if name != "running" else None
                self.assertEqual(row.status, case["expect"])
                if name == "running":
                    self.assertEqual(row.watermark, "wm-0")
                await _cancel(result)

    async def test_job_start_sets_running_without_touching_messages(self) -> None:
        clock = _Clock()
        messages = _over_threshold_messages("wm-1")
        state = _state(messages, summary="")
        before = list(messages)
        seeds = [
            None,
            CompactionRow(thread_id="t-1", status="applied", summary="OLD-SUMMARY"),
            CompactionRow(thread_id="t-1", status="discarded", summary="OLD-SUMMARY"),
            CompactionRow(
                thread_id="t-1",
                status="failed",
                summary="OLD-SUMMARY",
                failed_at=clock.t - 30,
            ),
        ]
        for seed in seeds:
            with self.subTest(status=None if seed is None else seed.status):
                store = MemoryCompactionStore()
                if seed is not None:
                    await store.upsert(seed)
                summarizer = _RecordingSummarizer()
                result = await plan_compact(
                    state,
                    store,
                    thread_id="t-1",
                    summarizer=summarizer,
                    now=clock,
                )
                await summarizer.started.wait()
                row = await store.get("t-1")
                assert row is not None
                self.assertEqual(row.status, "running")
                self.assertEqual(row.watermark, "wm-1")
                self.assertEqual(state["messages"], before)
                self.assertEqual(state["conversation_summary"], "")
                self.assertNotIn("messages", result.update)
                self.assertNotIn("conversation_summary", result.update)
                if seed is None:
                    self.assertEqual(row.summary, "")
                else:
                    self.assertEqual(row.summary, "OLD-SUMMARY")
                await _cancel(result)

    async def test_success_overwrites_summary_and_clears_error(self) -> None:
        store = MemoryCompactionStore()
        await store.upsert(
            CompactionRow(thread_id="t-1", status="applied", summary="OLD", error="stale")
        )
        summarizer = _RecordingSummarizer(
            SummaryResult(text="NEW-SUMMARY", input_tokens=1, output_tokens=1)
        )
        result = await plan_compact(
            _state(_over_threshold_messages("wm-2")),
            store,
            thread_id="t-1",
            summarizer=summarizer,
            now=_Clock(),
        )
        summarizer.release.set()
        assert result.job is not None
        await result.job
        row = await store.get("t-1")
        assert row is not None
        self.assertEqual(row.status, "ready")
        self.assertEqual(row.summary, "NEW-SUMMARY")
        self.assertEqual(row.watermark, "wm-2")
        self.assertEqual(row.error, "")

    async def test_ready_row_stores_five_token_counts(self) -> None:
        enc = tiktoken.get_encoding("o200k_base")
        summary = enc.decode(enc.encode("hello world " * 800)[:400])
        self.assertEqual(len(enc.encode(summary)), 400)
        messages = [
            {"id": "wm", "role": "assistant", "content": "p", "token_count": 30400},
            {"id": "keep", "role": "user", "content": "k", "token_count": 19600},
        ]
        store = MemoryCompactionStore()
        summarizer = _RecordingSummarizer(
            SummaryResult(text=summary, input_tokens=12000, output_tokens=300)
        )
        result = await plan_compact(
            _state(messages),
            store,
            thread_id="t-1",
            summarizer=summarizer,
            now=_Clock(),
        )
        summarizer.release.set()
        assert result.job is not None
        await result.job
        row = await store.get("t-1")
        assert row is not None
        self.assertEqual(row.token_count_before, 50000)
        self.assertEqual(row.estimated_token_count_after, 20000)
        self.assertEqual(row.summary_token_count, 400)
        self.assertEqual(row.summarizer_input_tokens, 12000)
        self.assertEqual(row.summarizer_output_tokens, 300)

    def test_summarizer_reasoning_effort_and_max_tokens(self) -> None:
        llm = MagicMock()
        llm.with_structured_output.return_value = MagicMock()
        with patch(_SUMMARIZER_LLM, return_value=llm) as ctor:
            SummarizerRunner(api_key="sk-test")
        self.assertEqual(ctor.call_args.kwargs["reasoning_effort"], "medium")
        self.assertEqual(ctor.call_args.kwargs["max_completion_tokens"], 2500)

    async def test_structured_output_fields_and_headings(self) -> None:
        parsed = ConversationSummary(
            current_user_goal="goal",
            decisions_made="decided",
            constraints_and_preferences="prefer short",
            important_entities_and_values="paper 2401.00001",
            what_has_been_done="searched",
            open_items="still open",
        )
        structured = MagicMock()

        async def ainvoke(prompt):
            return {"parsed": parsed, "raw": None}

        structured.ainvoke = ainvoke
        llm = MagicMock()
        llm.with_structured_output.return_value = structured
        with patch(_SUMMARIZER_LLM, return_value=llm):
            runner = SummarizerRunner(api_key="sk-test")
        schema = llm.with_structured_output.call_args.args[0]
        self.assertEqual(list(schema.model_fields), list(_FIELDS))
        store = MemoryCompactionStore()
        result = await plan_compact(
            _state(_over_threshold_messages("wm-2")),
            store,
            thread_id="t-1",
            summarizer=runner,
            now=_Clock(),
        )
        assert result.job is not None
        await result.job
        row = await store.get("t-1")
        assert row is not None
        positions = [row.summary.index(heading) for heading in _HEADINGS]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(len(positions), 6)

    async def test_summarizer_input_is_prefix_through_watermark(self) -> None:
        messages = [
            {"id": "b", "role": "user", "content": "BEFORE-MARK", "token_count": 4000},
            {"id": "w", "role": "assistant", "content": "AT-MARK", "token_count": 4000},
            {"id": "a", "role": "user", "content": "AFTER-MARK", "token_count": 40001},
        ]
        summarizer = _RecordingSummarizer()
        result = await plan_compact(
            _state(messages, summary="PRIOR-GOAL"),
            MemoryCompactionStore(),
            thread_id="t-1",
            summarizer=summarizer,
            now=_Clock(),
        )
        await summarizer.started.wait()
        prompt = summarizer.prompts[0]
        self.assertIn("PRIOR-GOAL", prompt)
        self.assertIn("BEFORE-MARK", prompt)
        self.assertIn("AT-MARK", prompt)
        self.assertNotIn("AFTER-MARK", prompt)
        await _cancel(result)

    async def test_summarizer_exception_sets_failed_and_keeps_summary(self) -> None:
        store = MemoryCompactionStore()
        await store.upsert(
            CompactionRow(thread_id="t-1", status="applied", summary="OLD-SUMMARY")
        )
        summarizer = _RecordingSummarizer(error=RuntimeError("boom"))
        result = await plan_compact(
            _state(_over_threshold_messages("wm-1")),
            store,
            thread_id="t-1",
            summarizer=summarizer,
            now=_Clock(),
        )
        summarizer.release.set()
        assert result.job is not None
        await result.job
        row = await store.get("t-1")
        assert row is not None
        self.assertEqual(row.status, "failed")
        self.assertIn("boom", row.error)
        self.assertEqual(row.summary, "OLD-SUMMARY")

    async def test_summarizer_timeout_at_90_seconds_sets_failed(self) -> None:
        store = MemoryCompactionStore()
        await store.upsert(
            CompactionRow(thread_id="t-1", status="applied", summary="OLD-SUMMARY")
        )

        async def fake_wait(coro, timeout):
            self.assertEqual(timeout, 90)
            coro.close()
            raise TimeoutError()

        with patch("plan_based_researcher.compaction.asyncio.wait_for", fake_wait):
            result = await plan_compact(
                _state(_over_threshold_messages("wm-1")),
                store,
                thread_id="t-1",
                summarizer=_RecordingSummarizer(),
                now=_Clock(),
            )
            assert result.job is not None
            await result.job
        row = await store.get("t-1")
        assert row is not None
        self.assertEqual(row.status, "failed")
        self.assertEqual(row.summary, "OLD-SUMMARY")

    async def test_compaction_does_not_write_transcript_items(self) -> None:
        spy = _SpyTranscript()
        store = MemoryCompactionStore()
        summarizer = _RecordingSummarizer(
            SummaryResult(text="NEW-SUMMARY", input_tokens=1, output_tokens=1)
        )
        result = await plan_compact(
            _state(_over_threshold_messages("wm-1")),
            store,
            thread_id="t-1",
            summarizer=summarizer,
            now=_Clock(),
            transcript=spy,
        )
        self.assertEqual((spy.inserts, spy.updates, spy.deletes), (0, 0, 0))
        summarizer.release.set()
        assert result.job is not None
        await result.job
        ready = await store.get("t-1")
        assert ready is not None
        self.assertEqual(ready.status, "ready")
        self.assertEqual((spy.inserts, spy.updates, spy.deletes), (0, 0, 0))

    def test_summarizer_model_and_exclusion_from_plan_agents(self) -> None:
        spec = REGISTRY["summarizer"]
        self.assertEqual(spec.name, "summarizer")
        self.assertEqual(spec.model, "gpt-5.6-luna")
        self.assertEqual(spec.tools, ())
        self.assertNotIn("summarizer", PLAN_AGENTS)
        self.assertNotIn("summarizer", planner_prompt_abilities())


if __name__ == "__main__":
    unittest.main()
