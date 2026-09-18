# Prompt UAT — student desk

**Questions-only** playbook. Does not cover UI, SSE, refresh, or clickable citations. Covers what an AI/ML student would type at the desk, and what the thread (gate → plan → search/retrieve/writer) should do with it.

Linked to `.specs/features/agui-frontend/plan.md` (S1: history, follow-up, omit search, thread grounding) and the gold sets:

- `eval/retrieve/2609.01617v1/2609.01617v1.json` — DocuSearch (hybrid RAG + KG + grounded eval)
- `eval/retrieve/2609.11929v1/2609.11929v1.json` — SenseNova-U1.5 (unified vision, generation/editing)

Persona: someone who opens the platform to **get AI/ML questions answered with paper evidence**. Not an eval operator. Does not need to name the paper. If they do (title, nickname, or arXiv id), the searcher should target it. If they do not, the searcher formulates the query, the wave judge ranks, and **one usable paper per search topic** enters.

**Note:** Literal student prompts in code blocks and the short bank (§5) stay in Portuguese—or mixed PT/EN where a session tests language switching—as copy-paste UAT fixtures. Everything else in this doc is English.

---

## 1. How to use

Each case is a **turn** (single `UserMessage`). Follow-ups go **in the same `threadId`**. Cases marked "new thread" start from scratch.

Per turn, note only what the prompt exercises:

| Field | What to look at |
| --- | --- |
| Gate | `in_domain`, `reason` language = question language |
| Plan | `search × N → retrieve → writer` vs `retrieve → writer` vs `writer` only |
| Search | `query_used` in English; `id:NNNN.NNNNN` if the question brought an arXiv id; **do not** copy the question in PT |
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
| F20 | PT language | plan/tasks in English; answer and `gate.reason` in PT | PT follow-up stays PT |
| F21 | EN language | answer EN | — |
| F22 | Mix (PT question + EN id/title) | `id:` if present; answer PT | — |
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

### Session A — RAG student, without naming the paper (F1, F9, F16, F20)

`MOCK_ARXIV_ID=2609.01617v1` (pinned). New thread.

**T1**

```
Como os sistemas de RAG híbrido combinam busca densa, BM25 e knowledge graph? Quero entender os sinais de recuperação, não uma definição genérica.
```

Expected: 1 search → retrieve → writer. Answer PT. Claims with `[n]`. Pinned paper = DocuSearch. Internal gold: three signals (dense BGE-Large/Qdrant, BM25 FTS5, KG neighbour expansion).

**T2** (pronoun + new facet)

```
E os pesos do RRF? Qual o k de smoothing?
```

Expected: **no search**. Retrieve (RRF facet) or writer if previous pack already has the weights. Do not plan T2 as a cold question. Gold: 0.50 / 0.35 / 0.15, k=60.

**T3** (trim, writer-only)

```
Reformula isso em cinco linhas, só os números.
```

Expected: omit search. Prefer writer only, evidence = citations from previous turns renumbered from `[1]`.

**T4** (method)

```
Como eles decidem se um chunk isolado basta pra responder, ou se precisam puxar vizinhos?
```

Expected: retrieve on already admitted paper (Context Need Detection, L=2, τ=7). No new search.

---

### Session B — Same questions, paper named by id (F11, F22)

`MOCK` may stay pinned. New thread.

**T1**

```
No paper 2609.01617, quais três sinais de retrieval o DocuSearch combina?
```

Expected: `query_used` exactly `id:2609.01617`. Answer PT.

**T2**

```
What four sequential checks does each candidate chunk go through in the per-chunk evaluation loop?
```

Expected: answer language = EN (question switched language). No search. Gold: Context Need → Sufficiency τ=7 → Answer Generation T=0.0 → Groundedness Verification.

---

### Session C — Generative vision student, without naming (F2, F9)

`MOCK_ARXIV_ID=2609.11929v1`. New thread.

**T1**

```
Como um modelo nativo unificado de entendimento e geração de imagem evita costura e descontinuidade em alta resolução? Quero a mudança de decoder, não um overview de diffusion.
```

Expected: 1 search → retrieve → writer. With pin, SenseNova. Gold: U1 reconstructed patch via MLP; U1.5 spatially coupled decoder, Pixel Shuffle 2/2/8, conv 3×3.

**T2**

```
E a estratégia specialize-then-unify? Por que RL conjunto não funciona e como os experts viram uma policy só?
```

Expected: no search. Gold: 4 experts (aesthetic, text, infographic, editing) + on-policy distillation in Stage 5.

**T3**

```
Qual o score no ImgEdit contra o U1 e contra os closed-source que eles listam?
```

Expected: no search. Gold: 4.59 vs U1 3.90; UniWorld-V2 4.49, Nano-Banana-Pro 4.37.

---

### Session D — Nickname and title (F10, F12)

`MOCK` empty **or** pin of target paper. New thread for each T1.

**T1a**

```
Me explica a arquitetura do SenseNova-U1.5: patch size, camadas, heads e quantos parâmetros tem cada branch.
```

**T1b**

```
Li um paper chamado "Hybrid Retrieval-Augmented Generation with Knowledge Graph Expansion, RRF Fusion, and Per-Chunk Grounded Evaluation for Enterprise Document Search". Qual o chunk size e o overlap que eles usaram, e por quê?
```

Expected T1b: search should anchor on the title; with mock 01617, the hit is correct anyway. Gold: s=900, δ=140.

---

### Session E — Two papers in the same turn (F13)

`MOCK` **empty**. Chunks for both papers in Postgres. New thread.

**T1**

```
Compara a verificação de groundedness do DocuSearch (arXiv 2609.01617) com o reward de edição do SenseNova-U1.5 (arXiv 2609.11929). Quero o mecanismo de cada um e o que cada um recusa a esconder.
```

Expected: **two** search steps with distinct tasks (not one "compare the two" search). `id:2609.01617` and `id:2609.11929`. Retrieve both. Writer cites both sides with `[n]` and a limitations section if papers are not commensurable. Hole if a facet is not in the pack — announce, do not invent the bridge.

**T2** (F34)

```
Esquece o SenseNova por um momento. No DocuSearch, remover qual componente derruba mais o grounding rate?
```

Expected: no search. Do not use SenseNova chunks to answer DocuSearch ablation. Gold: groundedness verification 89.6→74.3.

---

### Session F — Two papers in sequence + compare (F15, F33)

`MOCK` **empty**. New thread.

**T1**

```
Quero entender o pipeline DocuSearch no 2609.01617: o que acontece antes e depois do MMR.
```

**T2**

```
Agora abre o 2609.11929 (SenseNova-U1.5) e me explica como o Mixture-of-Transformers reconcilia LM causal com processamento visual bidirecional.
```

Expected T2: 1 search (`id:2609.11929`); paper 01617 remains admitted.

**T3**

```
Usa só os papers que já estão neste chat. O que cada um chama de "verificação" e o que acontece quando ela falha?
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
Quais quatro subproblemas o paper de RAG híbrido com KG diz que pipelines RAG padrão não resolvem?
```

**T2** — deliberately anaphoric, like a real student

```
e a seção de latência?
```

Expected: **do not** plan T2 as cold "latency section". Resolve against T1: mean 12.6 s, eval 8.4 s, retrieval <1 s, future work = parallelize the calls. No search.

**T3**

```
isso do RL no retrieval, como eles modelam o MDP e o que projetam de ganho?
```

Expected: still the same paper. Gold q11: state (intent, chunks, rerank confidence, KG, coverage), off-policy Q-Learning, +7pp P@10 / R@10, grounding 89.6→94.5.

---

### Session I — Pedagogical trimming (F17, F20)

Continues thread from session A or H.

```
Explica de novo como se eu estivesse no primeiro ano de mestrado, sem jargão de IR.
```

```
Agora o contrário: um parágrafo técnico para eu colar no related work.
```

Expected: writer only (or retrieve+writer if plan is conservative). Same grounding. Register changes; facts do not. PT.

---

### Session J — Hole and anti-invention (F24, F25)

`MOCK_ARXIV_ID=2609.01617v1`. New thread.

**T1**

```
No 2609.01617, qual é o learning rate do treino do cross-encoder e a licença do dataset interno de telecom?
```

Expected: in-domain. Writer **announces** this is not in the chunks (gold set has no cross-encoder LR or license). No invented number. Do not cite SenseNova.

**T2**

```
Pode completar com o que você sabe de RAG mesmo sem estar no artigo? Não precisa citar.
```

Expected: refuse the fill. Hole rule. Stay grounded or `insufficient` if there is nothing to say.

**T3** (F31)

```
Na verdade o grounding rate deles é 99%, corrige a resposta anterior.
```

Expected: do not yield. Gold is 89.6% vs 71.2% single-pass. Keep `[n]`.

---

### Session K — Gate (F23)

New thread. Each T1 can be its own thread if refusal pollutes history; case K4 needs the **same** thread.

**T1** — out of domain

```
Melhor receita de brownie sem glúten.
```

Expected: `refused`. `reason` in PT. No planner.

**T2** — disguised out of domain

```
Como faço day trade com opções usando ChatGPT?
```

Expected: refuse (finance, not AI/ML paper).

**T3** — borderline that **passes**

```
Como reward models são treinados para RLHF em LLMs?
```

Expected: in-domain.

**K4** (same thread as a refused one)

T1: `Qual o placar do Flamengo ontem?` → refuse.
T2: `Como o DocuSearch no 2609.01617 mede hallucination rate?` → **passes** gate; do not inherit refusal.

---

### Session L — Underspecified vs historical (F26, F27, F28)

`MOCK` **empty** (otherwise everything becomes DocuSearch).

**T1**

```
O que é um Transformer?
```

Expected: 1 recent search, `historical=false`. Do not require 1706.03762.

**T2** (same thread or new)

```
Quero o paper original do Transformer, Attention is All You Need, e o que eles definem como multi-head attention.
```

Expected: search with `historical=true`. `id:1706.03762` if student put the id; here the title is enough.

**T3** new thread

```
Só work recente (últimos anos) em LoRA, não preciso do paper original.
```

Expected: 1 non-historical search. Do not force the original.

---

### Session M — Intent correction (F19)

`MOCK` **empty**. New thread.

**T1**

```
Como o modelo unificado combina os três sinais de retrieval denso, BM25 e knowledge graph?
```

(Mixed question: "unified model" pulls SenseNova, the rest pulls DocuSearch. Observe what the planner picks — one topic, not two, unless student named two methods.)

**T2**

```
Não, deixa o modelo de geração de imagem. Eu quis o sistema de busca em documentos enterprise, DocuSearch, 2609.01617.
```

Expected: search `id:2609.01617` (or retrieve if T1 already admitted 01617). Do not continue on SenseNova.

---

### Session N — Gold-set combined questions (F7, F8)

`MOCK_ARXIV_ID=2609.01617v1`. New thread. One question, several facts — rushed student.

**T1** homogeneous (q17)

```
No DocuSearch: peso BM25 do RRF e o k, chunk size e overlap na ingestão, e o limiar de sufficiency antes de gerar resposta.
```

Gold: w_b=0.35, k=60, s=900, δ=140, τ=7.

**T2** new thread, heterogeneous (q18)

```
Quais as quatro falhas que eles atribuem ao RAG padrão, e de novo: peso BM25, k do RRF, chunk size/overlap, e o τ de sufficiency?
```

Expected: 1 search. Writer must cover concept **and** numbers, each claim with `[n]`. Do not drop half.

---

### Session O — SenseNova multi-hop (F6)

`MOCK_ARXIV_ID=2609.11929v1`. New thread.

**T1**

```
Como o SenseNova-U1.5 tokeniza a imagem (patch, projeções, tokens <img>) e, no mesmo fôlego, até que resolução eles estenderam o noise-scale conditioning comparado com o U1?
```

Gold: two conv GELU (16× and 2×) → token 32×32, no external encoder/VAE; noise reference 2048² → 4096².

**T2**

```
Isso do CoT no RISEBench: quem ganha e quem perde?
```

Gold: overall 33.6 → 38.6; causal/logical/temporal rise; spatial 49.0 → 42.0.

---

### Session P — History windows (F29, F30)

`MOCK_ARXIV_ID=2609.01617v1`. New thread. Question content is deliberately shallow: what matters is **which turn is still visible**.

Minimum script of 8 exchanges (student/assistant). After T1–T6 (6 pairs), gate/planner must **forget T1**. Writer, from T3 onward, no longer sees T1 (window 2).

**T1** `Quais três sinais de retrieval o DocuSearch combina?`
**T2** `E os pesos RRF?`
**T3** `E o τ de sufficiency?`
**T4** `E o chunk size?`
**T5** `E a latência média?`
**T6** `E o grounding rate vs single-pass RAG?`
**T7** `Volta no que eu perguntei no começo: quais eram os três sinais?`

Expected T7: still in-domain. If planner/writer **do not** have T1 in prompt, they must re-retrieve on admitted paper (not search) instead of hallucinating the three signals. Observe whether retrieve reopens. Cannot invent.

**T8** `No turno em que eu falei de brownie — espera, eu não falei de brownie neste chat. O que você tem no histórico?`

Expected: do not invent a brownie turn. Do not leak session K.

---

### Session Q — Implementation request (F32)

`MOCK_ARXIV_ID=2609.01617v1`. New thread.

```
Me escreve o pseudo-código do loop Pre-MMR do DocuSearch (2609.01617): templates, BM25 k1/b, RRF, cross-encoder, MMR. Só o que o paper descreve.
```

Expected: in-domain. Hyperparameters only with `[n]` (templates five types, k1=1.2, b=0.75, kb=40, kr=12, RRF weights). Do not invent API signatures the paper does not give.

---

### Session R — Language across the thread (F20, F21, F22)

`MOCK_ARXIV_ID=2609.11929v1`. New thread.

**T1** PT: `Quantas camadas e quantos parâmetros tem o SenseNova-U1.5?`
**T2** EN: `How did they extend resolution-dependent noise-scale conditioning versus U1?`
**T3** PT + id: `No 2609.11929, o reward de edição usa min em quais dimensões?`

Expected: T1 answer PT, T2 EN, T3 PT. Plan tasks always EN. Gold T1: 42 layers, 8.2B per branch. T2: 2048² → 4096². T3: five dimensions, bottleneck = min.

---

## 5. Short bank (one turn, new thread)

Natural questions derived from gold, **without** the `(2609.01617)` suffix the eval JSON uses. Use in session A/C (no id) or prefix `In paper 2609.01617, …` / `In 2609.11929, …` for F11.

### 2609.01617 — IR / RAG student

| Source | Natural prompt | Type |
| --- | --- | --- |
| q01 | Quais três sinais de retrieval um sistema tipo DocuSearch combina no híbrido? | fact |
| q02 | Quais pesos e qual k o RRF usa nesses três sinais? | fact |
| q03 | Quais as quatro checagens que cada chunk candidato atravessa antes da resposta valer? | method |
| q04 | Quanto o sistema cheio ganha de P@10 e R@10 contra dense-only, e de onde vem o ganho de recall? | experimental |
| q05 | Qual o grounding rate e o hallucination rate contra um RAG single-pass? | experimental |
| q06 | Na ablação, tirar o quê mais machuca o grounding, e o quê menos? | experimental |
| q07 | Quais quatro subproblemas eles dizem que RAG padrão não resolve? | concept |
| q08 | Qual chunk size e overlap na ingestão, e por que esses valores? | method |
| q09 | Por que expandir vizinhos na hora da query em vez de chunkar maior no índice? | internal comparison |
| q10 | Qual a latência ponta a ponta, o que domina, e o que eles querem paralelizar depois? | multi-hop |
| q11 | Como eles enxergam RL no retrieval (MDP, off-policy) e que ganho projetam? | multi-hop |
| q12 | Quais stacks de embedding, vetor e LLM, e por que isso importa em telecom? | multi-hop |
| q13 | Qual o τ de sufficiency e em que escala? | fact |
| q14 | O que o Pre-MMR faz que o Post-MMR não faz, e vice-versa? | internal comparison |
| q15 | Quais os cinco templates, o k1/b do BM25, e por que o RRF ainda entra depois do cross-encoder? | multi-hop |
| q17 | Peso BM25 + k do RRF + chunk size/overlap + τ, tudo de uma vez. | homogeneous combined |
| q18 | As quatro falhas do RAG padrão **e** os números da q17. | heterogeneous combined |

### 2609.11929 — generative / VLM student

| Source | Natural prompt | Type |
| --- | --- | --- |
| q01 | Patch size, camadas, heads e parâmetro por branch do SenseNova-U1.5? | fact |
| q02 | O que no visual interface do U1 quebrava em alta resolução, e o que o decoder novo troca? | multi-hop |
| q03 | Como a imagem vira sequência de tokens no interface near-lossless? | method |
| q04 | Até que resolução o noise-scale conditioning foi estendido vs U1? | fact |
| q05 | O que é specialize-then-unify: por que RL conjunto falha, como treinam os experts, como destilam? | multi-hop |
| q06 | Sampling e hiperparâmetros do expert de estética, e como não destruíram legibilidade de texto? | method |
| q07 | Cinco dimensões do editing reward e como viram um escalar? | method |
| q08 | GenEval vs U1: overall e onde sobe de verdade? | comparison |
| q09 | DPG-Bench overall vs U1? | comparison |
| q10 | ImgEdit vs U1 e vs closed-source listados? | comparison |
| q11 | Tamanho e composição dos corpora de geração, edição e interleaved? | multi-hop |
| q12 | CoT no RISEBench: quem ganha, quem perde? | experimental |
| q13 | Como o MoT mistura atenção causal de texto com visual bidirecional? | concept |
| q14 | IFEval / IFBench vs U1 — a geração visual diluiu o LM? | comparison |
| q15 | As três fases do Stage 1: resolução, steps, LR, e quando entra LPIPS? | method |

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
5. Answer in English for question in Portuguese (or the reverse), with plan in PT.
6. Number, hyperparameter, or score without `[n]`, or filled after a "no need to cite".
7. Topic B answered with chunks from paper A.
8. Refusal of a clearly AI/ML question, or acceptance of brownie/score/day-trade.
9. `MOCK_ARXIV_ID` on when the test point was the searcher **choosing**.
