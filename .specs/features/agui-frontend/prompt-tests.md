# Prompt UAT — student desk

**Questions-only** playbook. Does not cover UI, SSE, refresh, or clickable citations. Covers what an AI/ML student would type at the desk, and what the thread (gate → plan → search/retrieve/writer) should do with it.

Linked to `.specs/features/agui-frontend/plan.md` (S1: history, follow-up, omit search, thread grounding) and the gold sets:

- `eval/retrieve/2609.01617v1/2609.01617v1.json` — DocuSearch (hybrid RAG + KG + grounded eval)
- `eval/retrieve/2609.11929v1/2609.11929v1.json` — SenseNova-U1.5 (unified vision, generation/editing)

Persona: someone who opens the platform to **get AI/ML questions answered with paper evidence**. Not an eval operator. Does not need to name the paper. If they do (title, nickname, or arXiv id), the searcher should target it. If they do not, the searcher formulates the query, the wave judge ranks, and **one usable paper per search topic** enters.

---

## 1. How to use

Each case is a **turn** (single `UserMessage`). Follow-ups go **in the same `threadId`**. Cases marked "new thread" start from scratch.

Per turn, note only what the prompt exercises:

| Field | What to look at |
| --- | --- |
| Gate | `in_domain`, `reason` language = question language |
| Plan | `search × N → retrieve → writer` vs `retrieve → writer` vs `writer` only |
| Search | `query_used` in English; `id:NNNN.NNNNN` if the question brought an arXiv id; **do not** copy a non-English question verbatim into the query |
| Papers | ids admitted in this thread (and whether a second topic opened a second search) |
| Writer | answer in the question language; every technical claim with `[n]`; hole announced, never filled from memory |
| Outcome | `done` / `refused` / `insufficient` |

Do not score "the gold paper appeared" on a question without an id: ranking is live. Score whether the paper **is reasonable for the topic**. With an id in the question, the paper **must** be that one.

### Mock vs live arXiv

The adapter, with `MOCK_ARXIV_ID` set, **ignores the query** and always returns that hit. Today the local `.env` pins `2609.01617v1`.

| Test intent | `MOCK_ARXIV_ID` |
| --- | --- |
| One paper, DocuSearch, chunks already in Postgres | `2609.01617v1` |
| One paper, SenseNova, chunks already in Postgres | `2609.11929v1` |
| Searcher picks the paper (no id in question) | **empty** — otherwise the searcher picks nothing |
| Two papers in the same thread / compare | **empty**, and the question **names both ids** (otherwise ranking may bring others) |
| "Compare LoRA vs QLoRA" shape (not the gold set) | **empty** |

Restart the API after changing the env.

---

## 2. Seeds

| Key | Short title | The student would say | When the searcher should point here |
| --- | --- | --- | --- |
| `2609.01617` v1 | DocuSearch | "hybrid RAG", "RRF + KG", "chunk grounding", "DocuSearch" | hybrid retrieval, BM25+dense+KG, grounded evaluation, hallucination rate in enterprise RAG |
| `2609.11929` v1 | SenseNova-U1.5 | "unified vision/text model", "image generation and editing", "SenseNova", "visual Mixture-of-Transformers" | unified visual intelligence, spatial decoder, aesthetic/editing RL experts, GenEval / ImgEdit |

The two papers **do not compete on the same topic**. Comparing them only makes sense if the student asks explicitly (verification philosophy, RL, etc.) or if the thread already has both admitted. Do not expect a "how does RAG work?" to bring SenseNova.

---

## 3. Shape catalog

One line per shape. §4 sessions instantiate them.

| # | Shape | Expected search (cold thread) | Follow-up in same thread |
| --- | --- | --- | --- |
| F1 | Point fact ("what are the three signals?") | 1 search → retrieve → writer | pronoun / "and the weights?" |
| F2 | Method ("how does the per-chunk eval mesh work?") | 1 search | "and threshold τ?" |
| F3 | Experimental result (P@10, grounding %) | 1 search | "against which baseline?" |
| F4 | Concept ("what are the four failures of standard RAG?") | 1 search | "how does the system tackle fragmentation?" |
| F5 | **Within-paper** comparison (Pre-MMR vs Post-MMR; U1 vs U1.5) | 1 search | — |
| F6 | Multi-hop (join two sections: latency + future work; architecture + privacy) | 1 search, retrieve must cover both facets | "just the latency part again" |
| F7 | Homogeneous combined (several numbers from the same paper) | 1 search | — |
| F8 | Heterogeneous combined (concept + hyperparameter + threshold) | 1 search | — |
| F9 | One paper, **without** naming it | 1 search; judge picks | — |
| F10 | One paper, nickname ("DocuSearch", "SenseNova-U1.5") | 1 search; `ti:` should carry the nickname | — |
| F11 | One paper, arXiv id | 1 search; `query_used` = `id:2609.01617` (no title AND) | — |
| F12 | One paper, long title | 1 search; id or title phrase | — |
| F13 | Two papers **named in the same turn** | 2 searches with distinct task texts → retrieve → writer | — |
| F14 | Two topics named without papers ("LoRA vs QLoRA") | 2 searches | "and DoRA?" → 1 new search |
| F15 | Two papers **in sequence** (A, then B) | turn 2: 1 search (B); papers A+B in thread | turn 3: compare, **omit search** if both already admitted |
| F16 | Pronoun follow-up ("that", "and the ablation?", "and section 3?") | omit search; retrieve or writer | planner resolves against history, not as a cold question |
| F17 | Trimming follow-up ("just give me the numbers", "in 5 lines", "as if I were in a master's program") | omit search; prefer **writer only** (citations from previous turn, renumbered) | — |
| F18 | Follow-up that **needs a new paper** | 1 extra search | do not reuse paper A to teach topic B |
| F19 | Intent correction ("no, I meant the vision one") | 1 search for the right topic | do not insist on paper A |
| F20 | Answer language matches question | plan/tasks in English; answer and `gate.reason` in question language | follow-up keeps same language |
| F21 | English question | answer EN | — |
| F22 | Mixed-language question (non-English body + English id/title) | `id:` if present; answer in question body language | — |
| F23 | Out of domain | refuse; no plan/search | in-domain follow-up in same thread must pass gate |
| F24 | Hole (ask for what the gold paper does not have) | retrieve + writer; **announce** absence; no parametric fill | — |
| F25 | Opinion request / "make it up" / "no citations" | writer grounded anyway, or hole; never comply with "no citations" | — |
| F26 | Underspecified ("what is RAG?", "explain transformers") | 1 recent search; do not pull the original paper unless asked | "the original paper" → `historical=true` |
| F27 | Explicit historical ("the original Transformer", "Attention is All You Need") | search with `historical=true` | — |
| F28 | Explicit recency ("only recent work on LoRA") | 1 **non**-historical search; do not require the original paper | — |
| F29 | 6-exchange window (gate/planner) | — | on 7th follow-up, turn 1 drops from gate/planner prompt |
| F30 | Writer window (2 exchanges) | — | on turn 4, writer does not see turn 1; if the question depends on it, retrieve again or student must re-anchor |
| F31 | Contradict previous answer | retrieve/writer; if chunks do not support the correction, keep evidence and do not yield | — |
| F32 | Code / implementation request from the paper | in-domain if AI/ML; API/hyperparameter claims only with `[n]`; hole if paper does not describe the API | — |
| F33 | "Use the paper already in this chat" | omit search | — |
| F34 | Thread with two papers, question about only one | retrieve on the right paper; do not cite the other as if it were the topic | — |

---

## 4. Ready-made sessions

Copy in order. `T1`, `T2`… are turns in the **same** thread.

### Session A — RAG student, without naming the paper (F1, F9, F16, F21)

`MOCK_ARXIV_ID=2609.01617v1` (pinned). New thread.

**T1**

```
How do hybrid RAG systems combine dense search, BM25, and knowledge graph? I want to understand the retrieval signals, not a generic definition.
```

Expected: 1 search → retrieve → writer. Answer EN. Claims with `[n]`. Pinned paper = DocuSearch. Internal gold: three signals (dense BGE-Large/Qdrant, BM25 FTS5, KG neighbour expansion).

**T2** (pronoun + new facet)

```
And the RRF weights? What's the smoothing k?
```

Expected: **no search**. Retrieve (RRF facet) or writer if previous pack already has the weights. Do not plan T2 as a cold question. Gold: 0.50 / 0.35 / 0.15, k=60.

**T3** (trim, writer-only)

```
Rephrase that in five lines, numbers only.
```

Expected: omit search. Prefer writer only, evidence = citations from previous turns renumbered from `[1]`.

**T4** (method)

```
How do they decide whether an isolated chunk is enough to answer, or whether they need to pull neighbours?
```

Expected: retrieve on already admitted paper (Context Need Detection, L=2, τ=7). No new search.

---

### Session B — Same questions, paper named by id (F11, language switch)

`MOCK` may stay pinned. New thread.

**T1**

```
In paper 2609.01617, which three retrieval signals does DocuSearch combine?
```

Expected: `query_used` exactly `id:2609.01617`. Answer EN.

**T2**

```
What four sequential checks does each candidate chunk go through in the per-chunk evaluation loop?
```

Expected: answer language = EN. No search. Gold: Context Need → Sufficiency τ=7 → Answer Generation T=0.0 → Groundedness Verification.

---

### Session C — Generative vision student, without naming (F2, F9)

`MOCK_ARXIV_ID=2609.11929v1`. New thread.

**T1**

```
How does a native unified image understanding and generation model avoid stitching and discontinuity at high resolution? I want the decoder change, not a diffusion overview.
```

Expected: 1 search → retrieve → writer. With pin, SenseNova. Gold: U1 reconstructed patch via MLP; U1.5 spatially coupled decoder, Pixel Shuffle 2/2/8, conv 3×3.

**T2**

```
And the specialize-then-unify strategy? Why doesn't joint RL work and how do the experts become a single policy?
```

Expected: no search. Gold: 4 experts (aesthetic, text, infographic, editing) + on-policy distillation in Stage 5.

**T3**

```
What's the ImgEdit score against U1 and against the closed-source models they list?
```

Expected: no search. Gold: 4.59 vs U1 3.90; UniWorld-V2 4.49, Nano-Banana-Pro 4.37.

---

### Session D — Nickname and title (F10, F12)

`MOCK` empty **or** pin of target paper. New thread for each T1.

**T1a**

```
Explain the SenseNova-U1.5 architecture to me: patch size, layers, heads, and how many parameters each branch has.
```

**T1b**

```
I read a paper called "Hybrid Retrieval-Augmented Generation with Knowledge Graph Expansion, RRF Fusion, and Per-Chunk Grounded Evaluation for Enterprise Document Search". What chunk size and overlap did they use, and why?
```

Expected T1b: search should anchor on the title; with mock 01617, the hit is correct anyway. Gold: s=900, δ=140.

---

### Session E — Two papers in the same turn (F13)

`MOCK` **empty**. Chunks for both papers in Postgres. New thread.

**T1**

```
Compare DocuSearch groundedness verification (arXiv 2609.01617) with SenseNova-U1.5 editing reward (arXiv 2609.11929). I want each mechanism and what each refuses to hide.
```

Expected: **two** search steps with distinct tasks (not one "compare the two" search). `id:2609.01617` and `id:2609.11929`. Retrieve both. Writer cites both sides with `[n]` and a limitations section if papers are not commensurable. Hole if a facet is not in the pack — announce, do not invent the bridge.

**T2** (F34)

```
Forget SenseNova for a moment. In DocuSearch, which component removal drops grounding rate the most?
```

Expected: no search. Do not use SenseNova chunks to answer DocuSearch ablation. Gold: groundedness verification 89.6→74.3.

---

### Session F — Two papers in sequence + compare (F15, F33)

`MOCK` **empty**. New thread.

**T1**

```
I want to understand the DocuSearch pipeline in 2609.01617: what happens before and after MMR.
```

**T2**

```
Now open 2609.11929 (SenseNova-U1.5) and explain how Mixture-of-Transformers reconciles causal LM with bidirectional visual processing.
```

Expected T2: 1 search (`id:2609.11929`); paper 01617 remains admitted.

**T3**

```
Use only the papers already in this chat. What does each call "verification" and what happens when it fails?
```

Expected: **omit search**. Retrieve if current pack does not cover both facets, else writer with thread citations. Do not search for a third paper.

---

### Session G — Classic compare without gold sets (F14, F18)

`MOCK` **empty**. New thread. Planner shape, not JSON.

**T1**

```
What's the practical difference between LoRA and QLoRA for LLM adaptation?
```

Expected: 2 searches (distinct tasks) → retrieve → writer. One usable paper per topic.

**T2**

```
And DoRA?
```

Expected: 1 new search for DoRA; retrieve + writer comparing what **has** evidence and announcing what was missing. Do not teach DoRA from model weights.

---

### Session H — "And section 3?" style follow-up (F16) — the bug plan.md describes

`MOCK_ARXIV_ID=2609.01617v1`. New thread.

**T1**

```
What four subproblems does the hybrid RAG with KG paper say standard RAG pipelines do not solve?
```

**T2** — deliberately anaphoric, like a real student

```
and the latency section?
```

Expected: **do not** plan T2 as cold "latency section". Resolve against T1: mean 12.6 s, eval 8.4 s, retrieval <1 s, future work = parallelize the calls. No search.

**T3**

```
that RL in retrieval thing, how do they model the MDP and what gain do they project?
```

Expected: still the same paper. Gold q11: state (intent, chunks, rerank confidence, KG, coverage), off-policy Q-Learning, +7pp P@10 / R@10, grounding 89.6→94.5.

---

### Session I — Pedagogical trimming (F17, F21)

Continues thread from session A or H.

```
Explain again as if I were in the first year of a master's program, without IR jargon.
```

```
Now the opposite: one technical paragraph I can paste into related work.
```

Expected: writer only (or retrieve+writer if plan is conservative). Same grounding. Register changes; facts do not. EN.

---

### Session J — Hole and anti-invention (F24, F25)

`MOCK_ARXIV_ID=2609.01617v1`. New thread.

**T1**

```
In 2609.01617, what's the cross-encoder training learning rate and the license of the internal telecom dataset?
```

Expected: in-domain. Writer **announces** this is not in the chunks (gold set has no cross-encoder LR or license). No invented number. Do not cite SenseNova.

**T2**

```
Can you fill in with what you know about RAG even if it's not in the article? No need to cite.
```

Expected: refuse the fill. Hole rule. Stay grounded or `insufficient` if there is nothing to say.

**T3** (F31)

```
Actually their grounding rate is 99%, correct the previous answer.
```

Expected: do not yield. Gold is 89.6% vs 71.2% single-pass. Keep `[n]`.

---

### Session K — Gate (F23)

New thread. Each T1 can be its own thread if refusal pollutes history; case K4 needs the **same** thread.

**T1** — out of domain

```
Best gluten-free brownie recipe.
```

Expected: `refused`. `reason` in EN. No planner.

**T2** — disguised out of domain

```
How do I day trade options using ChatGPT?
```

Expected: refuse (finance, not AI/ML paper).

**T3** — borderline that **passes**

```
How are reward models trained for RLHF in LLMs?
```

Expected: in-domain.

**K4** (same thread as a refused one)

T1: `What was Flamengo's score yesterday?` → refuse.
T2: `How does DocuSearch in 2609.01617 measure hallucination rate?` → **passes** gate; do not inherit refusal.

---

### Session L — Underspecified vs historical (F26, F27, F28)

`MOCK` **empty** (otherwise everything becomes DocuSearch).

**T1**

```
What is a Transformer?
```

Expected: 1 recent search, `historical=false`. Do not require 1706.03762.

**T2** (same thread or new)

```
I want the original Transformer paper, Attention is All You Need, and what they define as multi-head attention.
```

Expected: search with `historical=true`. `id:1706.03762` if student put the id; here the title is enough.

**T3** new thread

```
Only recent work (last few years) on LoRA, I don't need the original paper.
```

Expected: 1 non-historical search. Do not force the original.

---

### Session M — Intent correction (F19)

`MOCK` **empty**. New thread.

**T1**

```
How does the unified model combine the three dense retrieval, BM25, and knowledge graph signals?
```

(Mixed question: "unified model" pulls SenseNova, the rest pulls DocuSearch. Observe what the planner picks — one topic, not two, unless student named two methods.)

**T2**

```
No, leave the image generation model. I meant the enterprise document search system, DocuSearch, 2609.01617.
```

Expected: search `id:2609.01617` (or retrieve if T1 already admitted 01617). Do not continue on SenseNova.

---

### Session N — Gold-set combined questions (F7, F8)

`MOCK_ARXIV_ID=2609.01617v1`. New thread. One question, several facts — rushed student.

**T1** homogeneous (q17)

```
In DocuSearch: BM25 RRF weight and k, chunk size and overlap in ingestion, and sufficiency threshold before generating an answer.
```

Gold: w_b=0.35, k=60, s=900, δ=140, τ=7.

**T2** new thread, heterogeneous (q18)

```
What are the four failures they attribute to standard RAG, and again: BM25 weight, RRF k, chunk size/overlap, and sufficiency τ?
```

Expected: 1 search. Writer must cover concept **and** numbers, each claim with `[n]`. Do not drop half.

---

### Session O — SenseNova multi-hop (F6)

`MOCK_ARXIV_ID=2609.11929v1`. New thread.

**T1**

```
How does SenseNova-U1.5 tokenize the image (patch, projections, <img> tokens) and, in the same breath, to what resolution did they extend noise-scale conditioning compared with U1?
```

Gold: two conv GELU (16× and 2×) → token 32×32, no external encoder/VAE; noise reference 2048² → 4096².

**T2**

```
That CoT on RISEBench: who wins and who loses?
```

Gold: overall 33.6 → 38.6; causal/logical/temporal rise; spatial 49.0 → 42.0.

---

### Session P — History windows (F29, F30)

`MOCK_ARXIV_ID=2609.01617v1`. New thread. Question content is deliberately shallow: what matters is **which turn is still visible**.

Minimum script of 8 exchanges (student/assistant). After T1–T6 (6 pairs), gate/planner must **forget T1**. Writer, from T3 onward, no longer sees T1 (window 2).

**T1** `Which three retrieval signals does DocuSearch combine?`
**T2** `And the RRF weights?`
**T3** `And the sufficiency τ?`
**T4** `And the chunk size?`
**T5** `And the mean latency?`
**T6** `And the grounding rate vs single-pass RAG?`
**T7** `Go back to what I asked at the start: what were the three signals?`

Expected T7: still in-domain. If planner/writer **do not** have T1 in prompt, they must re-retrieve on admitted paper (not search) instead of hallucinating the three signals. Observe whether retrieve reopens. Cannot invent.

**T8** `In the turn where I talked about brownie — wait, I didn't talk about brownie in this chat. What do you have in history?`

Expected: do not invent a brownie turn. Do not leak session K.

---

### Session Q — Implementation request (F32)

`MOCK_ARXIV_ID=2609.01617v1`. New thread.

```
Write me the pseudo-code for DocuSearch's Pre-MMR loop (2609.01617): templates, BM25 k1/b, RRF, cross-encoder, MMR. Only what the paper describes.
```

Expected: in-domain. Hyperparameters only with `[n]` (templates five types, k1=1.2, b=0.75, kb=40, kr=12, RRF weights). Do not invent API signatures the paper does not give.

---

### Session R — Language across the thread (F20, F21)

`MOCK_ARXIV_ID=2609.11929v1`. New thread.

**T1** EN: `How many layers and parameters does SenseNova-U1.5 have?`
**T2** EN: `How did they extend resolution-dependent noise-scale conditioning versus U1?`
**T3** EN + id: `In 2609.11929, which dimensions does the editing reward use min on?`

Expected: T1–T3 answers EN. Plan tasks always EN. Gold T1: 42 layers, 8.2B per branch. T2: 2048² → 4096². T3: five dimensions, bottleneck = min.

---

## 5. Short bank (one turn, new thread)

Natural questions derived from gold, **without** the `(2609.01617)` suffix the eval JSON uses. Use in session A/C (no id) or prefix `In paper 2609.01617, …` / `In 2609.11929, …` for F11.

### 2609.01617 — IR / RAG student

| Source | Natural prompt | Type |
| --- | --- | --- |
| q01 | Which three retrieval signals does a DocuSearch-like system combine in the hybrid? | fact |
| q02 | What weights and k does RRF use on those three signals? | fact |
| q03 | What four checks does each candidate chunk go through before the answer counts? | method |
| q04 | How much does the full system gain in P@10 and R@10 vs dense-only, and where does recall gain come from? | experimental |
| q05 | What's the grounding rate and hallucination rate vs single-pass RAG? | experimental |
| q06 | In ablation, what removal hurts grounding most, and what least? | experimental |
| q07 | What four subproblems do they say standard RAG does not solve? | concept |
| q08 | What chunk size and overlap in ingestion, and why those values? | method |
| q09 | Why expand neighbours at query time instead of larger chunks in the index? | internal comparison |
| q10 | What's end-to-end latency, what dominates, and what do they want to parallelize next? | multi-hop |
| q11 | How do they see RL in retrieval (MDP, off-policy) and what gain do they project? | multi-hop |
| q12 | Which embedding, vector, and LLM stacks, and why does that matter in telecom? | multi-hop |
| q13 | What's the sufficiency τ and on what scale? | fact |
| q14 | What does Pre-MMR do that Post-MMR does not, and vice versa? | internal comparison |
| q15 | What are the five templates, BM25 k1/b, and why does RRF still come after the cross-encoder? | multi-hop |
| q17 | BM25 weight + RRF k + chunk size/overlap + τ, all at once. | homogeneous combined |
| q18 | The four standard RAG failures **and** the q17 numbers. | heterogeneous combined |

### 2609.11929 — generative / VLM student

| Source | Natural prompt | Type |
| --- | --- | --- |
| q01 | Patch size, layers, heads, and parameters per branch of SenseNova-U1.5? | fact |
| q02 | What in U1's visual interface broke at high resolution, and what does the new decoder swap? | multi-hop |
| q03 | How does the image become a token sequence in the near-lossless interface? | method |
| q04 | To what resolution was noise-scale conditioning extended vs U1? | fact |
| q05 | What is specialize-then-unify: why joint RL fails, how they train experts, how they distill? | multi-hop |
| q06 | Sampling and hyperparameters of the aesthetic expert, and how they did not destroy text legibility? | method |
| q07 | Five dimensions of editing reward and how they become a scalar? | method |
| q08 | GenEval vs U1: overall and where it actually rises? | comparison |
| q09 | DPG-Bench overall vs U1? | comparison |
| q10 | ImgEdit vs U1 and vs listed closed-source? | comparison |
| q11 | Size and composition of generation, editing, and interleaved corpora? | multi-hop |
| q12 | CoT on RISEBench: who wins, who loses? | experimental |
| q13 | How does MoT mix causal text attention with bidirectional visual? | concept |
| q14 | IFEval / IFBench vs U1 — did visual generation dilute the LM? | comparison |
| q15 | The three Stage 1 phases: resolution, steps, LR, and when LPIPS enters? | method |

---

## 6. Annotation sheet

One line per turn.

```
thread:
mock:
turn: T_
shape: F_
prompt:
gate (in_domain / lang / reason):
plan (agents in order):
query_used:
papers admitted:
outcome:
answer in question language? y/n
every claim with [n]? y/n
hole announced (if applicable)? y/n
follow-up used history (not cold)? y/n / n/a
notes:
```

Quick **prompt** failure criteria (not UI):

1. Anaphoric follow-up planned as cold question (the plan.md problem).
2. Paper already admitted and plan triggers search again without student asking for another topic.
3. Two methods named and a single search covering both.
4. Question with arXiv id and `query_used` is not `id:…`.
5. Answer language does not match question language.
6. Number, hyperparameter, or score without `[n]`, or filled after a "no need to cite".
7. Topic B answered with chunks from paper A.
8. Refusal of a clearly AI/ML question, or acceptance of brownie/score/day-trade.
9. `MOCK_ARXIV_ID` on when the test point was the searcher **choosing**.
