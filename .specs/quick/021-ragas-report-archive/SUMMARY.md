# Summary: 021 RAGAS report archive

Collections `ascore` returned only a float. The report now keeps NLI statement/verdict/reason rows and the synthetic questions used for AnswerRelevancy, prints them, and appends JSON/Markdown plus `index.jsonl` under `reports/ragas/` so the git history can hold evals over time.
