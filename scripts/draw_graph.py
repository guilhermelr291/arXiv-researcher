"""Compile the research graph and write a Mermaid PNG (no Postgres, no LLM calls)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

from plan_based_researcher.agents.factory import AgentFactory
from plan_based_researcher.eval.strategies import (
    RetrieveEvalStrategy,
    SearchEvalStrategy,
)
from plan_based_researcher.graph.build import GraphDeps, build_graph

_ROOT = Path(__file__).resolve().parents[1]


class _StubFactory:
    def create(self, name: str) -> object:
        raise RuntimeError("draw_graph does not run agents")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Draw the compiled LangGraph as a Mermaid PNG."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=_ROOT / "graph.png",
        help="PNG path (default: graph.png at repo root)",
    )
    parser.add_argument(
        "--mermaid",
        type=Path,
        nargs="?",
        const=_ROOT / "graph.mmd",
        default=None,
        help="Also write Mermaid source (default path: graph.mmd at repo root)",
    )
    args = parser.parse_args()

    deps = GraphDeps(
        factory=cast(AgentFactory, _StubFactory()),
        search_eval=SearchEvalStrategy(api_key=None),
        retrieve_eval=RetrieveEvalStrategy(api_key=None),
    )
    drawable = build_graph(deps).get_graph()

    output = args.output if args.output.is_absolute() else Path.cwd() / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    drawable.draw_mermaid_png(output_file_path=str(output))
    print(f"Wrote {output}")

    if args.mermaid is not None:
        mermaid_path = (
            args.mermaid if args.mermaid.is_absolute() else Path.cwd() / args.mermaid
        )
        mermaid_path.parent.mkdir(parents=True, exist_ok=True)
        mermaid_path.write_text(drawable.draw_mermaid(), encoding="utf-8")
        print(f"Wrote {mermaid_path}")


if __name__ == "__main__":
    main()
