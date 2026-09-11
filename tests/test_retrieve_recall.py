"""Writer-visible Recall@k, including table/equation expand_hits injection."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plan_based_researcher.eval.retrieve_recall import (
    ItemRun,
    QrelAtom,
    RetrieveDataset,
    RetrieveItem,
    filter_dataset,
    paper_report_key,
    recall_at_k,
    report_output_paths,
    report_as_dict,
    report_from_item_runs,
    report_markdown,
    resolve_dataset_path,
    score_question,
)

_TABLE_BODY = (
    "TABLE V: Ablation Study: Grounding Rate\n"
    "| Configuration | Grounding Rate |\n"
    "| Full DocuSearch | 89.6% |"
)
_EQ_BODY = "E = mc^2"


def _score(*, required, evidence, ks=(5, 10, 15), atoms=None):
    return score_question(
        question_id="q06",
        query="ablation (2609.01617)",
        required_chunk_ids=required,
        evidence_chunks=evidence,
        ks=ks,
        qrel_atoms=atoms,
    )


class RecallAtKTest(unittest.TestCase):
    def test_eight_of_ten_is_point_eight(self) -> None:
        relevant = {f"c{i}" for i in range(10)}
        ranked = [f"c{i}" for i in range(8)] + ["x", "y"]
        self.assertEqual(recall_at_k(relevant, ranked, 10), 0.8)

    def test_short_pack_does_not_invent_slots(self) -> None:
        self.assertEqual(recall_at_k({"a", "b"}, ["a"], 15), 0.5)

    def test_k_must_be_at_least_one(self) -> None:
        with self.assertRaises(ValueError):
            recall_at_k({"a"}, ["a"], 0)


class WriterVisibleRecallTest(unittest.TestCase):
    def test_direct_id_hit_is_not_injected(self) -> None:
        gold = "7b32bea3-a51c-46f2-bf30-bd5cdbf55dde"
        row = _score(
            required=[gold],
            evidence=[{"chunk_id": gold, "excerpt": _TABLE_BODY}],
            atoms={gold: QrelAtom(kind="table", content=_TABLE_BODY)},
        )
        for item in row.scores:
            self.assertEqual(item.recall, 1.0)
            self.assertEqual(item.hits, (gold,))
            self.assertEqual(item.injected, ())

    def test_table_body_in_host_excerpt_is_hit(self) -> None:
        gold = "7b32bea3-a51c-46f2-bf30-bd5cdbf55dde"
        host = "2aaa7f5f-bd2d-4e45-8ecb-7a0d061083a2"
        excerpt = f"Table V shows grounding rate.\n{_TABLE_BODY}\nNo component is redundant."
        row = _score(
            required=[gold],
            evidence=[{"chunk_id": host, "excerpt": excerpt}],
            atoms={gold: QrelAtom(kind="table", content=_TABLE_BODY)},
        )
        for item in row.scores:
            self.assertEqual(item.recall, 1.0)
            self.assertEqual(item.hits, (gold,))
            self.assertEqual(item.misses, ())
            self.assertEqual(len(item.injected), 1)
            self.assertEqual(item.injected[0].chunk_id, gold)
            self.assertEqual(item.injected[0].host_chunk_id, host)
            self.assertEqual(item.injected[0].kind, "table")

    def test_equation_body_in_host_excerpt_is_hit(self) -> None:
        gold = "eq-1"
        host = "prose-1"
        row = _score(
            required=[gold],
            evidence=[{"chunk_id": host, "excerpt": f"see {_EQ_BODY} here"}],
            atoms={gold: QrelAtom(kind="equation", content=_EQ_BODY)},
        )
        self.assertEqual(row.scores[0].recall, 1.0)
        self.assertEqual(row.scores[0].injected[0].kind, "equation")

    def test_prose_qrel_is_not_injected_from_another_excerpt(self) -> None:
        gold = "prose-gold"
        host = "other"
        body = "Groundedness verification has the largest individual impact."
        row = _score(
            required=[gold],
            evidence=[{"chunk_id": host, "excerpt": body}],
            atoms={gold: QrelAtom(kind="prose", content=body)},
        )
        self.assertEqual(row.scores[0].recall, 0.0)
        self.assertEqual(row.scores[0].misses, (gold,))
        self.assertEqual(row.scores[0].injected, ())

    def test_table_absent_from_excerpt_is_miss(self) -> None:
        gold = "table-gold"
        row = _score(
            required=[gold],
            evidence=[{"chunk_id": "host", "excerpt": "unrelated prose"}],
            atoms={gold: QrelAtom(kind="table", content=_TABLE_BODY)},
        )
        self.assertEqual(row.scores[0].recall, 0.0)
        self.assertEqual(row.scores[0].injected, ())

    def test_without_qrel_atoms_injection_does_not_count(self) -> None:
        gold = "table-gold"
        row = _score(
            required=[gold],
            evidence=[{"chunk_id": "host", "excerpt": _TABLE_BODY}],
        )
        self.assertEqual(row.scores[0].recall, 0.0)
        self.assertEqual(row.scores[0].injected, ())

    def test_injection_requires_host_inside_k(self) -> None:
        gold = "table-gold"
        filler = [{"chunk_id": f"p{i}", "excerpt": "pad"} for i in range(5)]
        host = {"chunk_id": "host", "excerpt": _TABLE_BODY}
        row = _score(
            required=[gold],
            evidence=filler + [host],
            ks=(5, 10),
            atoms={gold: QrelAtom(kind="table", content=_TABLE_BODY)},
        )
        at5, at10 = row.scores
        self.assertEqual(at5.k, 5)
        self.assertEqual(at5.recall, 0.0)
        self.assertEqual(at5.injected, ())
        self.assertEqual(at10.recall, 1.0)
        self.assertEqual(at10.injected[0].host_chunk_id, "host")

    def test_report_annotates_injected_table(self) -> None:
        gold = "7b32bea3-a51c-46f2-bf30-bd5cdbf55dde"
        host = "2aaa7f5f-bd2d-4e45-8ecb-7a0d061083a2"
        dataset = RetrieveDataset(
            arxiv_id="2609.01617",
            version="1",
            title="t",
            items=(
                RetrieveItem(
                    id="q06",
                    query="ablation (2609.01617)",
                    required_chunk_ids=(gold,),
                ),
            ),
        )
        run = ItemRun(
            query="ablation (2609.01617)",
            thread_id="t1",
            outcome="done",
            stop_reason="writer_skipped",
            evidence_chunks=[{"chunk_id": host, "excerpt": _TABLE_BODY}],
            retrieve_query_used="ablation table",
            retrieve_task="extract ablation",
            admitted_papers=({"arxiv_id": "2609.01617", "version": "1"},),
            plan=[],
        )
        report = report_from_item_runs(
            dataset,
            [run],
            ks=(5,),
            qrel_atoms={gold: QrelAtom(kind="table", content=_TABLE_BODY)},
        )
        self.assertEqual(report.macro[5], 1.0)
        self.assertEqual(report.micro[5], 1.0)
        payload = report_as_dict(report)
        injected = payload["items"][0]["scores"][0]["injected"]
        self.assertEqual(injected[0]["chunk_id"], gold)
        self.assertEqual(injected[0]["host_chunk_id"], host)
        markdown = report_markdown(report)
        self.assertIn("Injected:", markdown)
        self.assertIn(gold, markdown)
        self.assertIn(host, markdown)
        self.assertIn("table", markdown)
        self.assertIn("misses: (none)", markdown)


class FilterDatasetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = RetrieveDataset(
            arxiv_id="2609.01617",
            version="1",
            title="t",
            items=(
                RetrieveItem(id="q01", query="one (2609.01617)", required_chunk_ids=("a",)),
                RetrieveItem(id="q02", query="two (2609.01617)", required_chunk_ids=("b",)),
            ),
        )

    def test_none_keeps_all_items(self) -> None:
        filtered = filter_dataset(self.dataset, None)
        self.assertEqual([item.id for item in filtered.items], ["q01", "q02"])

    def test_item_id_keeps_only_that_row(self) -> None:
        filtered = filter_dataset(self.dataset, "q02")
        self.assertEqual(len(filtered.items), 1)
        self.assertEqual(filtered.items[0].id, "q02")
        self.assertEqual(filtered.arxiv_id, "2609.01617")

    def test_unknown_item_id_raises(self) -> None:
        with self.assertRaises(ValueError) as caught:
            filter_dataset(self.dataset, "q99")
        self.assertIn("q99", str(caught.exception))
        self.assertIn("q01", str(caught.exception))


class ReportOutputPathsTest(unittest.TestCase):
    def test_paper_folder_uses_arxiv_id_and_version(self) -> None:
        self.assertEqual(paper_report_key("2609.01617", "1"), "2609.01617v1")

    def test_files_land_under_paper_folder(self) -> None:
        json_path, md_path, index_path = report_output_paths(
            Path("reports/retrieve"),
            arxiv_id="2609.01617",
            version="1",
            scored_at="2026-09-11T17:00:00Z",
        )
        self.assertEqual(
            json_path,
            Path("reports/retrieve/2609.01617v1/20260911T170000Z.json"),
        )
        self.assertEqual(md_path.suffix, ".md")
        self.assertEqual(index_path, Path("reports/retrieve/2609.01617v1/index.jsonl"))

    def test_item_id_suffixes_filename_inside_paper_folder(self) -> None:
        json_path, _, _ = report_output_paths(
            Path("reports/retrieve"),
            arxiv_id="2609.01617",
            version="1",
            scored_at="2026-09-11T17:00:00Z",
            item_id="q02",
        )
        self.assertEqual(
            json_path,
            Path("reports/retrieve/2609.01617v1/20260911T170000Z_q02.json"),
        )


class ResolveDatasetPathTest(unittest.TestCase):
    def test_nested_eval_retrieve_folder(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            nested = root / "eval" / "retrieve" / "2609.11929v1"
            nested.mkdir(parents=True)
            qrel = nested / "2609.11929v1.json"
            qrel.write_text("{}", encoding="utf-8")
            self.assertEqual(
                resolve_dataset_path("2609.11929v1.json", repo_root=root),
                qrel,
            )
            self.assertEqual(
                resolve_dataset_path("2609.11929v1", repo_root=root),
                qrel,
            )

    def test_existing_path_wins(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            other = root / "other.json"
            other.write_text("{}", encoding="utf-8")
            self.assertEqual(
                resolve_dataset_path(str(other), repo_root=root),
                other,
            )

    def test_missing_keeps_given_path(self) -> None:
        missing = Path("2609.11929v1.json")
        self.assertEqual(
            resolve_dataset_path(str(missing), repo_root=Path("/no-such-repo")),
            missing,
        )


if __name__ == "__main__":
    unittest.main()
