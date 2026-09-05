# Plan-Based Researcher

**Vision:** A plan-based multi-agent researcher that answers student AI/ML questions using only arXiv papers, with per-step evaluation and grounded generation.
**For:** Students who need didactic answers they can check against the paper passages that support each claim.
**Solves:** One-shot LLM answers mix parametric memory and the open web, so claims are unverifiable. A gated plan → research → evaluate → write loop over arXiv, with citations tied to retrieved chunks, produces inspectable answers.

## Goals

- Ship an async FastAPI SSE endpoint that runs Gate → Planner → Orchestrator loop → Researcher → Writer for a student query.
- Ground every technical claim in arXiv chunks (`[n]` + `citations[]`); refuse out-of-domain questions; emit insufficient evidence instead of hallucinating.
- Ship a Chainlit chat that streams research steps and opens citation excerpts in the side panel; resume the current chat via LangGraph `AsyncPostgresSaver`.

## Tech Stack

**Core:**

- Language: Python (>=3.12)
- API: FastAPI (async, `StreamingResponse` SSE)
- UI: Chainlit (host process; HTTP client of the API)
- Agent orchestration: LangGraph
- Database: PostgreSQL + pgvector (Docker)
- Checkpointer: LangGraph `AsyncPostgresSaver` (same Postgres)

**Key dependencies:** LangChain, LangGraph, langchain-community arXiv **search** tools (`ArxivRetriever` / `ArxivQueryRun`), `langchain_text_splitters`, BeautifulSoup/lxml/markdownify (HTML ingest), OpenAI (`gpt-5.1`, `gpt-5-mini`, `text-embedding-3-small`), Voyage `rerank-3` (retrieve scorer), Chainlit, psycopg/pgvector

## Scope

**v1 includes:**

- Domain gate (AI/ML only) before planning
- Planner + orchestrator evaluate/retry loop + arXiv researcher + grounded writer
- pgvector paper/chunk store with lazy **HTML** ingest, unique `(arxiv_id, version)`
- Single async `POST /research` SSE API and Chainlit UI
- Thread state in Postgres for the current Chainlit chat (`thread_id`)

**Explicitly out of scope:**

- Auth, multi-user accounts, billing, and a history product across anonymous browser sessions
- Web search (Tavily or otherwise) and non-arXiv paper APIs
- Dockerizing API/UI (Postgres only in Compose)
- Hover-citation JSX, `answer_delta`, HITL plan approval
- Native mobile/desktop clients

## Constraints

- All project artifacts (code, docs, comments, API contracts, prompts) must be in **English**. Student-facing answer language follows the query language.
- LLM and embeddings: OpenAI only.
- Evidence: arXiv only; category allowlist `cs.AI`, `cs.LG`, `cs.CL`, `cs.CV`, `cs.NE`, `cs.RO`, `stat.ML`.
- Caps: `max_steps=8`, **1 retry per step (2 attempts)**, `max_replans=1`, `max_papers=8`, timeout ~2 minutes. Retrieve: first-stage hybrid `retrieve_first_stage_k=40` per leg per paper, then adaptive cut `top_n=12` (not packed `retrieve_k_per_paper=5` from ensemble order).
- Splitter: heading split, then 512 / 50 (`cl100k_base`) **inside a section**; tables and display equations are never split. Feature spec: `.specs/features/arxiv-grounded-research/spec.md` (v1; loop IDs superseded by orchestrator-eval-replan). Loop spec: `.specs/features/orchestrator-eval-replan/spec.md`. Admission/retrieve amendment: `.specs/features/admission-retrieve-per-topic/spec.md` + `design.md` (approved 2026-08-29). Chunking: `.specs/features/structured-aware-chunking/spec.md` (HTML ingest, executed 2026-09-03). Rerank: `.specs/features/retrieve-cross-encoder-rerank/` (first-stage 40, adaptive cut `top_n=12`, Voyage Execute 2026-09-04; UAT pending). Architecture: `.specs/features/arxiv-grounded-research/context.md`.
