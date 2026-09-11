"""Score E2E retrieve writer-pack Recall@k with Writer off (RWR-04–RWR-07, RWR-09)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from plan_based_researcher.adapters.arxiv import ArxivPaperAdapter
from plan_based_researcher.adapters.hybrid import HybridRetrieveAdapter
from plan_based_researcher.adapters.voyage_embeddings import VoyageEmbeddingAdapter
from plan_based_researcher.agents.factory import AgentFactory
from plan_based_researcher.config import Settings
from plan_based_researcher.eval.retrieve_recall import (
    DEFAULT_KS,
    ItemRun,
    filter_dataset,
    load_dataset,
    missing_qrel_ids,
    qrel_atoms_from_chunks,
    report_as_dict,
    report_from_item_runs,
    report_markdown,
    report_output_paths,
    run_e2e_item,
)
from plan_based_researcher.eval.strategies import (
    RetrieveEvalStrategy,
    SearchEvalStrategy,
)
from plan_based_researcher.graph.build import GraphDeps
from plan_based_researcher.graph.research_graph import ResearchGraph
from plan_based_researcher.repo.chunks import PgChunkRepository

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DATASET = _REPO_ROOT / "eval" / "retrieve" / "2609.01617v1.json"
_DEFAULT_OUT_DIR = _REPO_ROOT / "reports" / "retrieve"


def main() -> None:
    args = _parse_args()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_run(args))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "E2E graph through retrieve, Writer off — not frozen RetrieveRunner. "
            "Report Recall@k on writer-visible evidence (packed ids plus "
            "table/equation bodies expanded into another excerpt)."
        )
    )
    parser.add_argument(
        "--dataset",
        default=str(_DEFAULT_DATASET),
        help=(
            "Qrel JSON path, or a filename under eval/retrieve/ "
            f"(default: {_DEFAULT_DATASET})."
        ),
    )
    parser.add_argument(
        "--item-id",
        default=None,
        help="Run and report only this dataset item id (e.g. q02).",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not write reports/retrieve JSON and Markdown (default: save).",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help=(
            "Parent directory for reports (default: reports/retrieve). "
            "JSON/Markdown are written under {out-dir}/{arxiv_id}v{version}/."
        ),
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    dataset_path = _resolve_dataset_path(args.dataset)
    dataset = load_dataset(dataset_path)
    try:
        dataset = filter_dataset(dataset, args.item_id)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2) from None
    settings = Settings()
    pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        kwargs={"autocommit": True, "row_factory": dict_row},
        open=False,
    )
    await pool.open()
    try:
        repo = PgChunkRepository(pool)
        if await repo.get_paper(dataset.arxiv_id, dataset.version) is None:
            print(
                f"Paper {dataset.arxiv_id}v{dataset.version} is not in Postgres. "
                "Ingest it before this report.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        if not await repo.paper_has_chunks(dataset.arxiv_id, dataset.version):
            print(
                f"Paper {dataset.arxiv_id}v{dataset.version} has no chunks.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        stored = await repo.list_chunks([(dataset.arxiv_id, dataset.version)])
        missing = missing_qrel_ids(
            {chunk.chunk_id for chunk in stored}, dataset.items
        )
        if missing:
            print(
                "Qrel chunk ids are missing from the ingested paper "
                "(re-ingest or regenerate the dataset):",
                file=sys.stderr,
            )
            for item_id, ids in missing.items():
                print(f"  {item_id}: {', '.join(ids)}", file=sys.stderr)
            raise SystemExit(2)

        embeddings = VoyageEmbeddingAdapter(api_key=settings.voyage_api_key)
        papers = ArxivPaperAdapter(mock_arxiv_id=settings.mock_arxiv_id or None)
        hybrid = HybridRetrieveAdapter(repo, embeddings)
        factory = AgentFactory(
            papers,
            repo,
            embeddings,
            hybrid,
            api_key=settings.openai_api_key,
            voyage_api_key=settings.voyage_api_key,
        )
        deps = GraphDeps(
            factory=factory,
            search_eval=SearchEvalStrategy(api_key=settings.openai_api_key),
            retrieve_eval=RetrieveEvalStrategy(api_key=settings.openai_api_key),
        )
        graph = ResearchGraph(deps, checkpointer=None, halt_before_writer=True)
        runs: list[ItemRun] = []
        for item in dataset.items:
            thread_id = str(uuid.uuid4())
            try:
                run = await run_e2e_item(
                    graph,
                    query=item.query,
                    thread_id=thread_id,
                    timeout_seconds=settings.research_timeout_seconds,
                )
            except Exception:
                runs.append(
                    ItemRun(
                        query=item.query,
                        thread_id=thread_id,
                        outcome="",
                        stop_reason="error",
                        evidence_chunks=[],
                        retrieve_query_used="",
                        retrieve_task="",
                        admitted_papers=(),
                        plan=[],
                    )
                )
            else:
                runs.append(run)
        report = report_from_item_runs(
            dataset,
            runs,
            ks=DEFAULT_KS,
            qrel_atoms=qrel_atoms_from_chunks(stored),
        )
    finally:
        await pool.close()

    markdown = report_markdown(report)
    print(markdown)
    if args.no_save:
        return
    out_dir = Path(args.out_dir) if args.out_dir else _DEFAULT_OUT_DIR
    payload = report_as_dict(report)
    payload["scored_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload["dataset"] = str(dataset_path)
    item_id = str(args.item_id).strip() if args.item_id else ""
    if item_id:
        payload["item_id"] = item_id
    _write_report(out_dir, payload, markdown)


def _resolve_dataset_path(raw: str) -> Path:
    path = Path(raw)
    if path.is_file():
        return path
    named = _REPO_ROOT / "eval" / "retrieve" / path.name
    if named.is_file():
        return named
    return path


def _write_report(out_dir: Path, payload: dict, markdown: str) -> Path:
    json_path, md_path, index_path = report_output_paths(
        out_dir,
        arxiv_id=str(payload["arxiv_id"]),
        version=str(payload["version"]),
        scored_at=str(payload["scored_at"]),
        item_id=str(payload.get("item_id") or ""),
    )
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(markdown, encoding="utf-8")
    relative = json_path.relative_to(out_dir).as_posix()
    index_line = {
        "scored_at": payload["scored_at"],
        "arxiv_id": payload["arxiv_id"],
        "version": payload["version"],
        "macro": payload["macro"],
        "micro": payload["micro"],
        "file": relative,
    }
    item_id = str(payload.get("item_id") or "").strip()
    if item_id:
        index_line["item_id"] = item_id
    with index_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(index_line, ensure_ascii=False) + "\n")
    print(f"Wrote {json_path}")
    return json_path


if __name__ == "__main__":
    main()
