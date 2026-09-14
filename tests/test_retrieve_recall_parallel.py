"""ARX-16: eval CLI item fan-out cap, dataset mock pin, pool size."""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import inspect
import unittest
from pathlib import Path

from plan_based_researcher.eval.retrieve_recall import (
    RetrieveDataset,
    RetrieveItem,
)

_ROOT = Path(__file__).resolve().parents[1]
_CLI = _ROOT / "scripts" / "retrieve_writer_recall.py"


def _load_run_e2e_items():
    spec = importlib.util.spec_from_file_location(
        "retrieve_writer_recall_cli", _CLI
    )
    if spec is None or spec.loader is None:
        raise ImportError(_CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run_e2e_items


run_e2e_items = _load_run_e2e_items()


def _cli_source() -> str:
    return _CLI.read_text(encoding="utf-8")


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _dataset(n: int) -> RetrieveDataset:
    items = tuple(
        RetrieveItem(
            id=f"q{i:02d}",
            query=f"query-{i} (2609.11929)",
            required_chunk_ids=("chunk-a",),
        )
        for i in range(n)
    )
    return RetrieveDataset(
        arxiv_id="2609.11929",
        version="1",
        title="fixture",
        items=items,
    )


def _ok_state(query: str) -> dict:
    return {
        "outcome": "done",
        "plan": [],
        "passed_steps": [],
        "papers": [],
        "retrieve_query_used": "",
        "evidence_chunks": [],
        "query": query,
    }


class _HoldGraph:
    def __init__(self, *, release: asyncio.Event) -> None:
        self.release = release
        self.in_flight = 0
        self.max_in_flight = 0
        self.started = 0
        self.thread_ids: list[str] = []

    def initial_graph_state(self, query: str) -> dict:
        return {"query": query}

    async def ainvoke(self, state: dict, config: dict) -> dict:
        self.started += 1
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        self.thread_ids.append(config["configurable"]["thread_id"])
        try:
            await self.release.wait()
            return _ok_state(str(state.get("query") or ""))
        finally:
            self.in_flight -= 1


class _OverlapGraph:
    def __init__(self, n: int) -> None:
        self._barrier = asyncio.Barrier(n)
        self.max_in_flight = 0
        self.in_flight = 0
        self.returns_before_all_started = 0
        self._n = n

    def initial_graph_state(self, query: str) -> dict:
        return {"query": query}

    async def ainvoke(self, state: dict, config: dict) -> dict:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await self._barrier.wait()
            return _ok_state(str(state.get("query") or ""))
        finally:
            self.in_flight -= 1


class _OrderedReleaseGraph:
    def __init__(self, n: int) -> None:
        self.releases = [asyncio.Event() for _ in range(n)]
        self.started = [asyncio.Event() for _ in range(n)]
        self.thread_ids: list[str] = []

    def initial_graph_state(self, query: str) -> dict:
        return {"query": query}

    async def ainvoke(self, state: dict, config: dict) -> dict:
        query = str(state.get("query") or "")
        idx = int(query.split("-")[1].split()[0])
        self.thread_ids.append(config["configurable"]["thread_id"])
        self.started[idx].set()
        await self.releases[idx].wait()
        return _ok_state(query)


def _item_index(query: str) -> int:
    return int(query.split("-")[1].split()[0])


class _RaiseAtGraph:
    def __init__(self, *, raise_at: int) -> None:
        self.raise_at = raise_at
        self.completed: list[str] = []

    def initial_graph_state(self, query: str) -> dict:
        return {"query": query}

    async def ainvoke(self, state: dict, config: dict) -> dict:
        query = str(state.get("query") or "")
        if _item_index(query) == self.raise_at:
            raise RuntimeError("item failed")
        await asyncio.sleep(0)
        self.completed.append(query)
        return _ok_state(query)


class _HangAtGraph:
    def __init__(self, *, hang_at: int) -> None:
        self.hang_at = hang_at
        self.completed: list[str] = []

    def initial_graph_state(self, query: str) -> dict:
        return {"query": query}

    async def ainvoke(self, state: dict, config: dict) -> dict:
        query = str(state.get("query") or "")
        if _item_index(query) == self.hang_at:
            await asyncio.sleep(3600)
        self.completed.append(query)
        return _ok_state(query)


class RetrieveRecallParallelTest(unittest.IsolatedAsyncioTestCase):
    async def test_six_items_at_most_five_ainvoke_in_flight(self) -> None:
        release = asyncio.Event()
        graph = _HoldGraph(release=release)
        dataset = _dataset(6)
        task = asyncio.create_task(
            run_e2e_items(graph, dataset.items, timeout_seconds=30)
        )
        for _ in range(50):
            if graph.max_in_flight >= 5:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
        self.assertEqual(graph.max_in_flight, 5)
        self.assertEqual(graph.started, 5)
        release.set()
        runs = await task
        self.assertEqual(len(runs), 6)
        self.assertLessEqual(graph.max_in_flight, 5)

    async def test_three_items_overlap_under_cap(self) -> None:
        graph = _OverlapGraph(3)
        dataset = _dataset(3)
        runs = await asyncio.wait_for(
            run_e2e_items(graph, dataset.items, timeout_seconds=30),
            timeout=2,
        )
        self.assertEqual(len(runs), 3)
        self.assertEqual(graph.max_in_flight, 3)
        self.assertLessEqual(graph.max_in_flight, 5)

    async def test_runs_align_to_dataset_order(self) -> None:
        graph = _OrderedReleaseGraph(6)
        dataset = _dataset(6)
        task = asyncio.create_task(
            run_e2e_items(graph, dataset.items, timeout_seconds=30)
        )
        await asyncio.wait_for(
            asyncio.gather(*(event.wait() for event in graph.started[:5])),
            timeout=2,
        )
        for idx in range(4, -1, -1):
            graph.releases[idx].set()
        await asyncio.wait_for(graph.started[5].wait(), timeout=2)
        graph.releases[5].set()
        runs = await task
        self.assertEqual(len(runs), 6)
        for i, item in enumerate(dataset.items):
            self.assertEqual(runs[i].query, item.query)

    async def test_one_raise_does_not_cancel_siblings(self) -> None:
        graph = _RaiseAtGraph(raise_at=2)
        dataset = _dataset(6)
        runs = await run_e2e_items(graph, dataset.items, timeout_seconds=30)
        self.assertEqual(len(runs), 6)
        self.assertEqual(runs[2].stop_reason, "error")
        self.assertEqual(runs[2].query, dataset.items[2].query)
        others = [run for i, run in enumerate(runs) if i != 2]
        self.assertTrue(all(run.stop_reason != "error" for run in others))
        self.assertEqual(len(graph.completed), 5)

    async def test_one_timeout_does_not_cancel_siblings(self) -> None:
        graph = _HangAtGraph(hang_at=2)
        dataset = _dataset(6)
        runs = await run_e2e_items(graph, dataset.items, timeout_seconds=0.05)
        self.assertEqual(len(runs), 6)
        self.assertEqual(runs[2].stop_reason, "timeout")
        self.assertEqual(runs[2].query, dataset.items[2].query)
        others = [run for i, run in enumerate(runs) if i != 2]
        self.assertTrue(all(run.stop_reason != "timeout" for run in others))
        self.assertEqual(len(graph.completed), 5)

    async def test_thread_ids_are_unique(self) -> None:
        release = asyncio.Event()
        release.set()
        graph = _HoldGraph(release=release)
        dataset = _dataset(6)
        runs = await run_e2e_items(graph, dataset.items, timeout_seconds=30)
        ids = [run.thread_id for run in runs]
        self.assertEqual(len(ids), 6)
        self.assertEqual(len(set(ids)), 6)
        self.assertTrue(all(thread_id for thread_id in ids))


class RetrieveRecallParallelAstTest(unittest.TestCase):
    def test_batch_uses_semaphore_gather_not_taskgroup(self) -> None:
        source = inspect.getsource(run_e2e_items)
        tree = ast.parse(source)
        semaphore_values: list[int] = []
        gather_return_exceptions: list[object] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node.func)
            if name == "Semaphore":
                if node.args and isinstance(node.args[0], ast.Constant):
                    semaphore_values.append(int(node.args[0].value))
            if name == "gather":
                for kw in node.keywords:
                    if kw.arg == "return_exceptions":
                        gather_return_exceptions.append(
                            kw.value.value
                            if isinstance(kw.value, ast.Constant)
                            else None
                        )
        self.assertIn(5, semaphore_values)
        self.assertIn(True, gather_return_exceptions)
        self.assertNotIn("TaskGroup", source)

    def test_cli_reports_after_item_batch(self) -> None:
        batch_src = inspect.getsource(run_e2e_items)
        self.assertNotIn("report_from_item_runs", batch_src)
        self.assertNotIn("_write_report", batch_src)
        tree = ast.parse(_cli_source())
        run_fn = None
        for node in tree.body:
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_run":
                run_fn = node
                break
        self.assertIsNotNone(run_fn)
        ordered: list[tuple[int, int, str]] = []
        for node in ast.walk(run_fn):
            if isinstance(node, ast.Call):
                name = _call_name(node.func)
                if name in {
                    "run_e2e_items",
                    "report_from_item_runs",
                    "_write_report",
                }:
                    ordered.append((node.lineno, node.col_offset, name))
        names = [name for _, _, name in sorted(ordered)]
        self.assertEqual(
            names,
            ["run_e2e_items", "report_from_item_runs", "_write_report"],
        )

    def test_cli_pins_mock_arxiv_id_to_dataset_paper(self) -> None:
        source = _cli_source()
        self.assertNotIn("settings.mock_arxiv_id", source)
        tree = ast.parse(source)
        found = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _call_name(node.func) != "ArxivPaperAdapter":
                continue
            found = True
            kwargs = {kw.arg: kw.value for kw in node.keywords}
            mock = kwargs.get("mock_arxiv_id")
            self.assertIsInstance(mock, ast.Call)
            self.assertEqual(_call_name(mock.func), "paper_report_key")
        self.assertTrue(found)

    def test_cli_pool_max_size_is_five(self) -> None:
        tree = ast.parse(_cli_source())
        sizes: list[int] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _call_name(node.func) != "AsyncConnectionPool":
                continue
            for kw in node.keywords:
                if kw.arg == "max_size" and isinstance(kw.value, ast.Constant):
                    sizes.append(int(kw.value.value))
        self.assertEqual(sizes, [5])


if __name__ == "__main__":
    unittest.main()
