# Agent notes

Product narrative: `README.md`. Numbers (caps, allowlist, splitter, hybrid, rerank cut): `src/plan_based_researcher/policy.py`. Agent names, abilities, models, tools: `src/plan_based_researcher/agents/registry.py`. Decisions: `.specs/project/STATE.md` (wins over older ADRs).

## Product

FastAPI SSE `POST /research` runs a LangGraph loop: gate → planner → dispatch → search|execute → evaluate → retry / remaining-suffix replan / finalize. Chainlit on port 8000 is an HTTP client of the API on 8001. Evidence is arXiv only.

## Commands

```bash
uv sync
uv run python -m unittest discover -s tests
uv run python -m unittest tests.test_<module>
uv run uvicorn plan_based_researcher.main:app --host 127.0.0.1 --port 8001
uv run chainlit run src/plan_based_researcher/ui/app.py --port 8000
```

Needs Docker Postgres (`docker compose up -d`), `OPENAI_API_KEY`, and `VOYAGE_API_KEY`. Health: `GET http://127.0.0.1:8001/health`. `thread_id` is required on `/research`.

Live eval (not the unit gate): `uv run python scripts/retrieve_writer_recall.py` → `reports/retrieve/`; `uv run python scripts/ragas_writer_report.py` → `reports/ragas/`. After an embedding-width change: `uv run python scripts/wipe_paper_chunks.py --yes` then restart (schema is CREATE-only). Cached UAT: `MOCK_ARXIV_ID` in `.env`.


## Git

Branches: `feat/<slug>` (kebab-case). Match `.specs/features/<slug>` when the work has a feature folder. Do not use a bare slug (`retrieve-t3-union-retry`).

Commits and push only after the user has reviewed the diff and asked. Finishing a task, a green test run, or tlc-spec-lean **build** does not authorize a commit — that skill's commit step is deferred here. When the user does ask, Conventional Commits (`type(scope): description`). Read-only git (`status`, `diff`, `log`) is always fine.


## Where to change what


| Concern                                      | Path                                                        |
| -------------------------------------------- | ----------------------------------------------------------- |
| Graph compile, nodes, state                  | `src/plan_based_researcher/graph/`                          |
| Agent prompts and runners                    | `src/plan_based_researcher/agents/`                         |
| Caps, allowlist, grounding, hole rule        | `policy.py` — do not copy into prompts                      |
| arXiv, hybrid, Voyage                        | `adapters/` implementing `ports/`                           |
| HTML parse, chunks, pack, expand, rerank cut | `ingest/`                                                   |
| Search/retrieve eval, writer-pack recall     | `eval/`                                                     |
| SSE product API                              | `api/` — `ResearchExecutor` is the only production iterator |
| Chainlit                                     | `ui/` — HTTP only                                           |
| pgvector                                     | `repo/`                                                     |
| Feature specs                                | `.specs/features/<name>/{spec,design,tasks}.md`             |
| Quick tasks                                  | `.specs/quick/`                                             |


Python ≥ 3.12, package `plan_based_researcher` under `src/`. `from __future__ import annotations`. Records: frozen dataclasses with `slots=True`.

## Invariants

1. **UI isolation.** `ui/` must not import `graph`, `agents`, or LangGraph. Chainlit pops `DATABASE_URL` on purpose — do not share it with the UI process.
2. **Registry + factory.** Bind runners by registry name. No `if/elif` agent dispatch. Planner prompt abilities come from `planner_prompt_abilities()`.
3. **Ports.** New I/O goes through `ports/` Protocols. App code does not `import voyageai`; embeddings and rerank use `langchain_voyageai`.
4. **Shared arXiv client.** Use the module-level client and `_REQUEST_LOCK` in `adapters/arxiv.py`. Parallel `Send("search")` must not 429 `export.arxiv.org`.
5. **English internals.** Plan `task`/`reasoning`, eval `feedback`, and search/retrieve/rerank queries stay English even when the student asks in Portuguese. Writer (and gate `reason`) follow the query language. Locks: `tests/test_internal_english.py`.
6. **Grounding.** Every technical claim needs a real `[n]` from packed chunks. Announce missing topics; never fill from model weights. Writer is one-shot: no Writer eval or retry.
7. **Retrieve path.** HTML ingest on cache miss `(arxiv_id, version)` → hybrid first-stage per paper → Voyage `rerank-3` on the English retrieve task → `cut_reranked` → `pack_hits` → `expand_hits`. One usable paper per search topic. Tables and display equations stay atomic.
8. `**halt_before_writer`** is eval-CLI only. FastAPI lifespan compiles with Writer on and a Postgres checkpointer. Do not DROP chunks on boot.
9. **SSE.** Production consume path is `astream_events` v2 + `StreamDispatcher`. Routes do not call `astream(`.
10. **Search ranking.** The search runner does not pick a paper. Consecutive search steps fan out with `Send`; the wave judge at eval ranks titles+abstracts.

## Tests

Stdlib `unittest` in `tests/`. Not pytest. Full gate: `uv run python -m unittest discover -s tests`. Do not call live OpenAI, Voyage, arXiv, Postgres, or LangSmith from unittest. Do not `import ragas` from `tests/`. Do not delete existing test modules — discover will silently shrink.

## Out of v1

Auth, multi-user history, web search, HITL plan approval, Dockerized API/UI (Postgres only in Compose).