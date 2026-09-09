# Summary: 020 RAGAS max_tokens

Faithfulness `ascore` truncated structured JSON (`instructor.IncompleteOutputException`). The report LLM now requests 16384 completion tokens (`RAGAS_MAX_TOKENS` override). If a judge still truncates, that trace is skipped and the process exits 0.
