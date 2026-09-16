"""Retrieve hops: formulate gate, per-topic Voyage, slot+RRF fusion."""

from __future__ import annotations

import asyncio
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from plan_based_researcher.adapters.hybrid import HybridResult
from plan_based_researcher.agents.query_schema import (
    FormulatedQuery,
    FormulatedRetrieveQuery,
)
from plan_based_researcher.agents.retrieve import (
    RetrieveRunner,
    fuse_hop_cuts,
    normalize_retrieve_hops,
)
from plan_based_researcher.agents.search import SearchRunner
from plan_based_researcher.ingest.rerank import build_rerank_query
from plan_based_researcher.policy import Policy
from plan_based_researcher.ports.chunks import ChunkRecord

_CHAT = "plan_based_researcher.agents.retrieve.ChatOpenAI"
_SEARCH_CHAT = "plan_based_researcher.agents.search.ChatOpenAI"
_SCORE = "plan_based_researcher.agents.retrieve.score_chunks"
_TRACE = "plan_based_researcher.agents.retrieve.trace"
_CUT = "plan_based_researcher.agents.retrieve.cut_reranked"
_TASK = "Retrieve BM25 parameters and why the cross-encoder keeps an RRF term"
_QUERY = "unused-union-query"
_PAPER = {
    "arxiv_id": "2609.01617",
    "version": "1",
    "title": "paper",
    "year": 2026,
    "url": "https://arxiv.org/abs/2609.01617",
    "categories": ["cs.LG"],
}
_PAPER_B = {
    "arxiv_id": "2609.11929",
    "version": "1",
    "title": "other",
    "year": 2026,
    "url": "https://arxiv.org/abs/2609.11929",
    "categories": ["cs.LG"],
}


def _chunk(chunk_id: str, *, arxiv_id: str = "2609.01617") -> ChunkRecord:
    return ChunkRecord(
        chunk_id=chunk_id,
        arxiv_id=arxiv_id,
        version="1",
        title="paper",
        year=2026,
        url=f"https://arxiv.org/abs/{arxiv_id}",
        kind="prose",
        unit_id=None,
        content=f"body {chunk_id}",
        metadata={"section": "V", "caption": "", "unit_ids": []},
    )


@asynccontextmanager
async def _fake_trace(*args, **kwargs):
    yield SimpleNamespace(end=lambda **k: None)


def _first_pass_state(*papers: dict) -> dict:
    return {
        "step_index": 1,
        "plan": [
            {"agent": "search", "task": "find papers"},
            {"agent": "retrieve", "task": _TASK},
            {"agent": "writer", "task": "write"},
        ],
        "passed_steps": [],
        "retry_counts": {},
        "papers": list(papers) or [_PAPER],
        "evidence_chunks": [],
        "retrieve_query_used": "",
        "eval_by_step": {},
        "hole_tasks": [],
        "search_artifacts": {},
        "query": "Quais os parametros BM25 e o termo RRF?",
    }


def _retry_state(*, hops: list[str]) -> dict:
    first = [
        {
            "chunk_id": f"keep-{i}",
            "n": i + 1,
            "arxiv_id": "2609.01617",
            "version": "1",
            "title": "paper",
            "year": 2026,
            "url": "https://arxiv.org/abs/2609.01617",
            "excerpt": f"keep {i}",
        }
        for i in range(3)
    ]
    state = _first_pass_state()
    state["retry_counts"] = {"1": 1}
    state["evidence_chunks"] = first
    state["retrieve_query_used"] = "previous hops"
    state["eval_by_step"] = {
        "1": {"feedback": "total corpus size gap", "step_index": 1}
    }
    return state


class _MapHybrid:
    def __init__(self, by_query: dict[str, list[str]], *, arxiv_id: str = "2609.01617") -> None:
        self.by_query = by_query
        self.calls: list[tuple[str, list, int]] = []
        self._arxiv_id = arxiv_id

    async def retrieve(self, query: str, paper_keys: list, k: int) -> HybridResult:
        self.calls.append((query, paper_keys, k))
        ids = self.by_query.get(query, [f"{query}-{i}" for i in range(k)])
        ranked = [_chunk(cid, arxiv_id=paper_keys[0][0]) for cid in ids[:k]]
        return HybridResult(ranked=ranked, corpus=ranked)


def _runner(hybrid, formulated) -> RetrieveRunner:
    formulate = MagicMock()
    formulate.ainvoke = AsyncMock(return_value=formulated)
    with patch(_CHAT) as chat:
        chat.return_value.with_structured_output.return_value = formulate
        runner = RetrieveRunner(
            papers=MagicMock(),
            chunks=MagicMock(),
            embeddings=MagicMock(),
            hybrid=hybrid,
            api_key="sk-test",
            voyage_api_key="v-test",
        )
    runner._formulate = formulate
    return runner


def _high_scores(chunks, query, api_key=""):
    return [0.9] * len(chunks)


class SchemaAndNormalizeTest(unittest.TestCase):
    def test_retrieve_schema_has_query_and_hops_search_query_only(self) -> None:
        retrieve_names = list(FormulatedRetrieveQuery.model_fields)
        self.assertEqual(retrieve_names, ["query", "hops"])
        search_names = list(FormulatedQuery.model_fields)
        self.assertEqual(search_names, ["query"])
        with patch(_CHAT) as chat:
            chat.return_value.with_structured_output.return_value = MagicMock()
            RetrieveRunner(
                papers=MagicMock(),
                chunks=MagicMock(),
                embeddings=MagicMock(),
                hybrid=MagicMock(),
                api_key="sk-test",
                voyage_api_key="v-test",
            )
        schema = chat.return_value.with_structured_output.call_args.args[0]
        self.assertIs(schema, FormulatedRetrieveQuery)
        with patch(_SEARCH_CHAT) as search_chat:
            search_chat.return_value.with_structured_output.return_value = MagicMock()
            SearchRunner(papers=MagicMock(), api_key="sk-test")
        search_schema = search_chat.return_value.with_structured_output.call_args.args[0]
        self.assertIs(search_schema, FormulatedQuery)

    def test_normalize_drops_empty_and_whitespace_hops(self) -> None:
        self.assertEqual(
            normalize_retrieve_hops(["  ", "", "bm25 k1 b", "\t"]),
            ["bm25 k1 b"],
        )

    def test_normalize_dedups_first_occurrence(self) -> None:
        self.assertEqual(
            normalize_retrieve_hops(["bm25", "rrf", "bm25", "rrf"]),
            ["bm25", "rrf"],
        )

    def test_normalize_caps_at_six_schema_prefix(self) -> None:
        hops = [f"h{i}" for i in range(7)]
        self.assertEqual(Policy.retrieve_hop_cap, 6)
        self.assertEqual(normalize_retrieve_hops(hops), hops[:6])


class FuseHopCutsTest(unittest.TestCase):
    def test_walk_packs_shared_overview_once_then_hop_golds(self) -> None:
        overview = _chunk("overview")
        gold_a = _chunk("gold-a")
        gold_b = _chunk("gold-b")
        fused = fuse_hop_cuts(
            [
                [overview, gold_a, _chunk("tail-a")],
                [overview, gold_b, _chunk("tail-b")],
            ]
        )
        ids = [row.chunk_id for row in fused]
        self.assertEqual(ids[:3], ["overview", "gold-b", "gold-a"])
        self.assertEqual(ids.count("overview"), 1)

    def test_seconds_fill_by_rrf_not_schema_tail(self) -> None:
        firsts = [f"F{i}" for i in range(1, 7)]
        seconds = {i: f"S{i}" for i in range(1, 7)}
        cuts = [
            [_chunk("F1"), *[_chunk(f) for f in firsts[1:]], _chunk("S1")],
            [_chunk("F2"), _chunk("F1"), *[_chunk(f) for f in firsts[2:]], _chunk("S2")],
            [_chunk("F3"), _chunk("F1"), _chunk("F2"), *[_chunk(f) for f in firsts[3:]], _chunk("S3")],
            [_chunk("F4"), _chunk("S4"), *[_chunk(f) for f in firsts if f not in {"F4"}]],
            [_chunk("F5"), _chunk("S5"), *[_chunk(f) for f in firsts if f not in {"F5"}]],
            [_chunk("F6"), _chunk("S6"), *[_chunk(f) for f in firsts if f not in {"F6"}]],
        ]
        fused = fuse_hop_cuts(cuts, pack_cap=10, rrf_k=60)
        ids = [row.chunk_id for row in fused]
        self.assertEqual(ids[:6], firsts)
        extras = ids[6:]
        self.assertEqual(len(extras), 4)
        self.assertIn("S6", extras)
        self.assertIn("S4", extras)
        self.assertIn("S5", extras)
        self.assertNotIn("S2", extras)
        self.assertNotIn("S3", extras)

    def test_overflow_rrf_k_sixty_on_cut_ranks(self) -> None:
        self.assertEqual(Policy.retrieve_hop_rrf_k, 60)
        hop_a = [_chunk("A1"), _chunk("A2"), _chunk("win"), _chunk("lose")]
        hop_b = [_chunk("B1"), _chunk("B2"), _chunk("win"), _chunk("lose")]
        fused = fuse_hop_cuts([hop_a, hop_b], pack_cap=5, rrf_k=60)
        ids = [row.chunk_id for row in fused]
        self.assertEqual(ids[:4], ["A1", "B1", "A2", "B2"])
        self.assertEqual(ids[4], "win")

    def test_citation_n_order_firsts_seconds_overflow(self) -> None:
        hop_a = [_chunk("F1"), _chunk("S1"), _chunk("O1")]
        hop_b = [_chunk("F2"), _chunk("S2"), _chunk("O2")]
        fused = fuse_hop_cuts([hop_a, hop_b], pack_cap=6, rrf_k=60)
        self.assertEqual(
            [row.chunk_id for row in fused],
            ["F1", "F2", "S1", "S2", "O1", "O2"],
        )


class RetrieveHopsRunnerTest(unittest.IsolatedAsyncioTestCase):
    async def test_first_pass_empty_hops_is_one_facet(self) -> None:
        hybrid = _MapHybrid({_QUERY: [f"c{i}" for i in range(40)]})
        runner = _runner(
            hybrid, FormulatedRetrieveQuery(query=_QUERY, hops=[])
        )
        cut_kwargs: list[dict] = []

        def _cut(pairs, **kwargs):
            cut_kwargs.append(kwargs)
            return [pair[0] for pair in pairs[: kwargs.get("top_n", 10)]]

        voyage_queries: list[str] = []

        def _score(chunks, query, api_key=""):
            voyage_queries.append(query)
            return [0.9] * len(chunks)

        with (
            patch(_SCORE, _score),
            patch(_TRACE, _fake_trace),
            patch(_CUT, _cut),
        ):
            await runner.run(_first_pass_state())
        self.assertEqual(len(hybrid.calls), 1)
        self.assertEqual(hybrid.calls[0][0], _QUERY)
        self.assertEqual(hybrid.calls[0][2], Policy.retrieve_first_stage_k)
        self.assertEqual(voyage_queries, [build_rerank_query(_TASK, "")])
        self.assertEqual(cut_kwargs[0]["top_n"], 10)
        self.assertEqual(cut_kwargs[0]["margin"], 0.20)
        self.assertEqual(cut_kwargs[0]["floor"], 0.30)

    async def test_first_pass_one_hop_is_one_facet(self) -> None:
        hybrid = _MapHybrid({_QUERY: [f"c{i}" for i in range(8)]})
        runner = _runner(
            hybrid,
            FormulatedRetrieveQuery(query=_QUERY, hops=["single-hop-terms"]),
        )
        voyage_queries: list[str] = []

        def _score(chunks, query, api_key=""):
            voyage_queries.append(query)
            return [0.9] * len(chunks)

        with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
            await runner.run(_first_pass_state())
        self.assertEqual([c[0] for c in hybrid.calls], [_QUERY])
        self.assertNotIn("single-hop-terms", [c[0] for c in hybrid.calls])
        self.assertEqual(voyage_queries, [build_rerank_query(_TASK, "")])

    async def test_first_pass_two_hops_is_multi_path(self) -> None:
        hops = ["bm25 k1 b", "cross encoder rrf"]
        hybrid = _MapHybrid({h: [f"{h}-{i}" for i in range(8)] for h in hops})
        runner = _runner(
            hybrid, FormulatedRetrieveQuery(query=_QUERY, hops=hops)
        )
        voyage_queries: list[str] = []

        def _score(chunks, query, api_key=""):
            voyage_queries.append(query)
            return [0.9] * len(chunks)

        with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
            await runner.run(_first_pass_state())
        self.assertEqual(sorted(c[0] for c in hybrid.calls), sorted(hops))
        self.assertNotIn(_QUERY, [c[0] for c in hybrid.calls])
        self.assertEqual(sorted(voyage_queries), sorted(hops))
        self.assertNotIn(_TASK, voyage_queries)

    async def test_multi_hybrid_once_per_hop_k_forty(self) -> None:
        hops = ["alpha hop", "beta hop"]
        papers = [_PAPER, _PAPER_B]
        hybrid = _MapHybrid({h: [f"{h}-{i}" for i in range(40)] for h in hops})
        runner = _runner(
            hybrid, FormulatedRetrieveQuery(query=_QUERY, hops=hops)
        )
        with patch(_SCORE, _high_scores), patch(_TRACE, _fake_trace):
            await runner.run(_first_pass_state(*papers))
        self.assertEqual(len(hybrid.calls), 4)
        for query, keys, k in hybrid.calls:
            self.assertIn(query, hops)
            self.assertEqual(k, 40)
            self.assertEqual(len(keys), 1)
        by_paper = {(c[1][0][0], c[0]) for c in hybrid.calls}
        self.assertEqual(
            by_paper,
            {
                ("2609.01617", "alpha hop"),
                ("2609.01617", "beta hop"),
                ("2609.11929", "alpha hop"),
                ("2609.11929", "beta hop"),
            },
        )

    async def test_multi_voyage_prefix_fifteen_hop_query(self) -> None:
        hop = "long hybrid list"
        ids = [f"d{i}" for i in range(40)]
        hybrid = _MapHybrid({hop: ids, "other hop": [f"o{i}" for i in range(40)]})
        runner = _runner(
            hybrid,
            FormulatedRetrieveQuery(query=_QUERY, hops=[hop, "other hop"]),
        )
        scored: list[tuple[str, list[str]]] = []

        def _score(chunks, query, api_key=""):
            scored.append((query, [c.chunk_id for c in chunks]))
            return [0.9] * len(chunks)

        with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
            await runner.run(_first_pass_state())
        self.assertEqual(Policy.retrieve_hop_voyage_docs, 15)
        by_query = {query: cids for query, cids in scored}
        self.assertEqual(by_query[hop], ids[:15])
        self.assertEqual(len(by_query["other hop"]), 15)

    async def test_hops_gather_papers_sequential(self) -> None:
        hops = ["hop-a", "hop-b"]
        order: list[str] = []
        release = asyncio.Event()

        class _Recording:
            async def retrieve(self, query: str, paper_keys: list, k: int) -> HybridResult:
                paper = paper_keys[0][0]
                if paper == "2609.11929":
                    p1_ends = sum(1 for e in order if e.startswith("end:2609.01617"))
                    if p1_ends < 2:
                        raise AssertionError(
                            "paper 2 started before paper 1 hops finished"
                        )
                order.append(f"start:{paper}:{query}")
                if paper == "2609.01617" and query == hops[0]:
                    await release.wait()
                elif paper == "2609.01617" and query == hops[1]:
                    release.set()
                order.append(f"end:{paper}:{query}")
                ranked = [_chunk(f"{paper}-{query}", arxiv_id=paper)]
                return HybridResult(ranked=ranked, corpus=ranked)

        runner = _runner(
            _Recording(), FormulatedRetrieveQuery(query=_QUERY, hops=hops)
        )
        with patch(_SCORE, _high_scores), patch(_TRACE, _fake_trace):
            await asyncio.wait_for(
                runner.run(_first_pass_state(_PAPER, _PAPER_B)),
                timeout=2,
            )
        first_p1_end = next(
            i for i, e in enumerate(order) if e.startswith("end:2609.01617")
        )
        self.assertEqual(
            len(
                [
                    e
                    for e in order[: first_p1_end + 1]
                    if e.startswith("start:2609.01617")
                ]
            ),
            2,
        )

    async def test_multi_retrieve_query_used_is_joined_hops(self) -> None:
        hops = ["bm25 templates", "rrf k"]
        hybrid = _MapHybrid({h: [f"{h}-1"] for h in hops})
        runner = _runner(
            hybrid, FormulatedRetrieveQuery(query=_QUERY, hops=hops)
        )
        with patch(_SCORE, _high_scores), patch(_TRACE, _fake_trace):
            out = await runner.run(_first_pass_state())
        self.assertEqual(out["retrieve_query_used"], "bm25 templates rrf k")
        self.assertNotEqual(out["retrieve_query_used"], _QUERY)

    async def test_multi_voyage_at_most_six_never_task(self) -> None:
        hops = [f"topic-{i}" for i in range(7)]
        hybrid = _MapHybrid({h: [f"{h}-1"] for h in hops})
        runner = _runner(
            hybrid, FormulatedRetrieveQuery(query=_QUERY, hops=hops)
        )
        voyage_queries: list[str] = []

        def _score(chunks, query, api_key=""):
            voyage_queries.append(query)
            return [0.9] * len(chunks)

        with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
            await runner.run(_first_pass_state())
        self.assertEqual(len(voyage_queries), 6)
        self.assertNotIn(_TASK, voyage_queries)
        self.assertNotIn("topic-6", voyage_queries)

    async def test_multi_rerank_span_records_hop_count(self) -> None:
        hops = ["one coverage", "two coverage"]
        captured: list[dict] = []

        @asynccontextmanager
        async def _capture_trace(*args, **kwargs):
            captured.append({"args": args, "kwargs": kwargs})
            yield SimpleNamespace(end=lambda **k: None)

        hybrid = _MapHybrid({h: [f"{h}-1"] for h in hops})
        runner = _runner(
            hybrid, FormulatedRetrieveQuery(query=_QUERY, hops=hops)
        )
        with patch(_SCORE, _high_scores), patch(_TRACE, _capture_trace):
            await runner.run(_first_pass_state())
        rerank = [row for row in captured if row["args"][:1] == ("rerank",)]
        self.assertTrue(rerank)
        payload = rerank[0]["kwargs"]
        blob = {**payload.get("inputs", {}), **payload.get("metadata", {})}
        self.assertGreaterEqual(int(blob["hop_count"]), 2)
        self.assertTrue(blob.get("used_hops") or blob.get("hops"))

    async def test_hop_cut_kwargs_top_n_fifteen(self) -> None:
        hops = ["cut-a", "cut-b"]
        hybrid = _MapHybrid({h: [f"{h}-{i}" for i in range(20)] for h in hops})
        runner = _runner(
            hybrid, FormulatedRetrieveQuery(query=_QUERY, hops=hops)
        )
        seen: list[dict] = []

        def _cut(pairs, **kwargs):
            seen.append(kwargs)
            return [pair[0] for pair in pairs[: kwargs.get("top_n", 15)]]

        with (
            patch(_SCORE, _high_scores),
            patch(_TRACE, _fake_trace),
            patch(_CUT, _cut),
        ):
            await runner.run(_first_pass_state())
        self.assertGreaterEqual(len(seen), 2)
        for kwargs in seen:
            self.assertEqual(kwargs["top_n"], 15)
            self.assertEqual(kwargs["margin"], 0.20)
            self.assertEqual(kwargs["floor"], 0.30)

    async def test_empty_hop_cut_contributes_zero_slots(self) -> None:
        hops = ["weak hop", "strong hop"]
        hybrid = _MapHybrid(
            {
                "weak hop": ["ensemble-only"],
                "strong hop": ["gold-strong"],
            }
        )
        runner = _runner(
            hybrid, FormulatedRetrieveQuery(query=_QUERY, hops=hops)
        )

        def _score(chunks, query, api_key=""):
            if query == "weak hop":
                return [0.05] * len(chunks)
            return [0.9] * len(chunks)

        with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
            out = await runner.run(_first_pass_state())
        ids = [row["chunk_id"] for row in out["evidence_chunks"]]
        self.assertIn("gold-strong", ids)
        self.assertNotIn("ensemble-only", ids)

    async def test_multi_paper_pack_at_most_ten(self) -> None:
        hops = [f"h{i}" for i in range(6)]
        hybrid = _MapHybrid(
            {h: [f"{h}-c{i}" for i in range(20)] for h in hops}
        )
        runner = _runner(
            hybrid, FormulatedRetrieveQuery(query=_QUERY, hops=hops)
        )
        with patch(_SCORE, _high_scores), patch(_TRACE, _fake_trace):
            out = await runner.run(_first_pass_state())
        self.assertLessEqual(len(out["evidence_chunks"]), 10)

    async def test_two_papers_concat_continuous_n(self) -> None:
        hops = ["facet-a", "facet-b"]
        hybrid = _MapHybrid({h: [f"{h}-x"] for h in hops})
        runner = _runner(
            hybrid, FormulatedRetrieveQuery(query=_QUERY, hops=hops)
        )
        with patch(_SCORE, _high_scores), patch(_TRACE, _fake_trace):
            out = await runner.run(_first_pass_state(_PAPER, _PAPER_B))
        ns = [row["n"] for row in out["evidence_chunks"]]
        self.assertEqual(ns, list(range(1, len(ns) + 1)))
        papers = [row["arxiv_id"] for row in out["evidence_chunks"]]
        first_b = papers.index("2609.11929")
        self.assertTrue(all(p == "2609.01617" for p in papers[:first_b]))

    async def test_one_hop_voyage_raise_others_still_fuse(self) -> None:
        hops = ["bad voyage", "good voyage"]
        hybrid = _MapHybrid(
            {"bad voyage": ["bad-id"], "good voyage": ["good-id"]}
        )
        runner = _runner(
            hybrid, FormulatedRetrieveQuery(query=_QUERY, hops=hops)
        )

        def _score(chunks, query, api_key=""):
            if query == "bad voyage":
                raise RuntimeError("voyage down")
            return [0.9] * len(chunks)

        with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
            out = await runner.run(_first_pass_state())
        ids = [row["chunk_id"] for row in out["evidence_chunks"]]
        self.assertEqual(ids, ["good-id"])
        self.assertNotIn("bad-id", ids)

    async def test_one_hop_hybrid_raise_others_still_fuse(self) -> None:
        hops = ["bad hybrid", "good hybrid"]

        class _Hybrid:
            async def retrieve(self, query: str, paper_keys: list, k: int) -> HybridResult:
                if query == "bad hybrid":
                    raise RuntimeError("hybrid down")
                ranked = [_chunk("good-hyb")]
                return HybridResult(ranked=ranked, corpus=ranked)

        runner = _runner(
            _Hybrid(), FormulatedRetrieveQuery(query=_QUERY, hops=hops)
        )
        with patch(_SCORE, _high_scores), patch(_TRACE, _fake_trace):
            out = await runner.run(_first_pass_state())
        ids = [row["chunk_id"] for row in out["evidence_chunks"]]
        self.assertEqual(ids, ["good-hyb"])

    async def test_hop_failure_does_not_fallback_to_task_voyage(self) -> None:
        hops = ["boom", "ok"]
        hybrid_queries: list[str] = []

        class _Hybrid:
            async def retrieve(self, query: str, paper_keys: list, k: int) -> HybridResult:
                hybrid_queries.append(query)
                if query == "boom":
                    raise RuntimeError("hybrid down")
                ranked = [_chunk("ok-id")]
                return HybridResult(ranked=ranked, corpus=ranked)

        voyage_queries: list[str] = []

        def _score(chunks, query, api_key=""):
            voyage_queries.append(query)
            return [0.9] * len(chunks)

        runner = _runner(
            _Hybrid(), FormulatedRetrieveQuery(query=_QUERY, hops=hops)
        )
        with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
            await runner.run(_first_pass_state())
        self.assertNotIn(_QUERY, hybrid_queries)
        self.assertNotIn(_TASK, voyage_queries)

    async def test_all_hops_empty_last_writes_evidence(self) -> None:
        hops = ["dead-a", "dead-b"]

        class _Hybrid:
            async def retrieve(self, query: str, paper_keys: list, k: int) -> HybridResult:
                raise RuntimeError("all hops fail")

        runner = _runner(
            _Hybrid(), FormulatedRetrieveQuery(query=_QUERY, hops=hops)
        )
        with patch(_SCORE, _high_scores), patch(_TRACE, _fake_trace):
            out = await runner.run(_first_pass_state())
        self.assertIn("evidence_chunks", out)
        self.assertEqual(out["evidence_chunks"], [])

    async def test_t3_retry_ignores_hops(self) -> None:
        hops = ["should-ignore-a", "should-ignore-b"]
        hybrid = _MapHybrid(
            {"total corpus size gap": [f"r{i}" for i in range(10)]}
        )
        runner = _runner(
            hybrid,
            FormulatedRetrieveQuery(query=_QUERY, hops=hops),
        )
        voyage_queries: list[str] = []

        def _score(chunks, query, api_key=""):
            voyage_queries.append(query)
            return [0.9] * len(chunks)

        with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
            await runner.run(_retry_state(hops=hops))
        self.assertEqual([c[0] for c in hybrid.calls], ["total corpus size gap"])
        self.assertEqual(voyage_queries, ["total corpus size gap"])

    async def test_t3_retry_single_voyage_call(self) -> None:
        hops = ["h1", "h2", "h3"]
        hybrid = _MapHybrid(
            {"total corpus size gap": [f"r{i}" for i in range(10)]}
        )
        runner = _runner(
            hybrid,
            FormulatedRetrieveQuery(query=_QUERY, hops=hops),
        )
        n_score = 0

        def _score(chunks, query, api_key=""):
            nonlocal n_score
            n_score += 1
            return [0.9] * len(chunks)

        with patch(_SCORE, _score), patch(_TRACE, _fake_trace):
            await runner.run(_retry_state(hops=hops))
        self.assertEqual(n_score, 1)


if __name__ == "__main__":
    unittest.main()
