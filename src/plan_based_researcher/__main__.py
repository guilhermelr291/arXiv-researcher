"""Run the research API with a psycopg-compatible event loop."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the research FastAPI process.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    import uvicorn

    uvicorn.run(
        "plan_based_researcher.main:app",
        host=args.host,
        port=args.port,
        loop="plan_based_researcher.selector_loop:new_selector_event_loop",
    )


if __name__ == "__main__":
    main()
