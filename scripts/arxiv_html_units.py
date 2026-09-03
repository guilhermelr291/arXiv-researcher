"""Debug CLI over ``parse_arxiv_html`` (not the production parser).

Fetches arXiv HTML, parses in-memory via the library, and may write
``_tmp_arxiv_html`` sidecars. Production retrieve must not import this script.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import httpx

from plan_based_researcher.ingest.html_parse import ParsedPaper, parse_arxiv_html
from plan_based_researcher.policy import Policy

_ROOT = Path(__file__).resolve().parents[1]
_USER_AGENT = (
    "plan-based-researcher-html-units/0.1 "
    "(local research spike; not a crawler; https://arxiv.org/help/robots)"
)
_TIMEOUT = httpx.Timeout(30.0)
_UNSAFE_ID = re.compile(r"[^\w.\-]+", re.UNICODE)
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


def main() -> None:
    args = _parse_args()
    _require_extras()

    arxiv_id = args.arxiv_id.strip()
    version = args.version.strip().lstrip("vV")
    html_url = Policy.html_url(arxiv_id, version)
    out = args.out or (_ROOT / "_tmp_arxiv_html" / f"{arxiv_id}v{version}")
    if not out.is_absolute():
        out = Path.cwd() / out

    html_bytes = _fetch(html_url)
    out.mkdir(parents=True, exist_ok=True)
    (out / "paper.html").write_bytes(html_bytes)

    parsed = parse_arxiv_html(html_bytes)
    if not parsed.usable:
        print(f"error: {parsed.reason} at {html_url}", file=sys.stderr)
        sys.exit(1)

    (out / "prose.md").write_text(parsed.prose_markdown, encoding="utf-8")
    (out / "sections.txt").write_text(
        _heading_outline(parsed.prose_markdown), encoding="utf-8"
    )

    units_dir = out / "units"
    if units_dir.exists():
        shutil.rmtree(units_dir)
    units_dir.mkdir()

    encoder = _token_encoder()
    chunk_size = Policy.chunk_size
    manifest = _write_units(parsed, units_dir=units_dir, encoder=encoder, chunk_size=chunk_size)

    (units_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    _print_report(parsed, manifest, encoder, chunk_size)
    print(f"Wrote {out}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch arXiv HTML and dump parse_arxiv_html sidecars "
            "(debug CLI, not the production parser)."
        )
    )
    parser.add_argument("arxiv_id", help="arXiv id (never infers latest by itself)")
    parser.add_argument("version", help="Version digit(s), e.g. 1 (required, never implicit)")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: _tmp_arxiv_html/{id}v{ver} at repo root)",
    )
    return parser.parse_args()


def _require_extras() -> None:
    try:
        import tiktoken  # noqa: F401
    except ImportError:
        print(
            "Missing local extra: tiktoken\nInstall with: pip install tiktoken",
            file=sys.stderr,
        )
        sys.exit(1)


def _fetch(url: str) -> bytes:
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        print(f"error: GET {url} failed: {exc}", file=sys.stderr)
        sys.exit(1)
    if response.status_code != 200:
        print(f"error: GET {url} returned {response.status_code}", file=sys.stderr)
        sys.exit(1)
    if not response.content:
        print(f"error: empty body from {url}", file=sys.stderr)
        sys.exit(1)
    return response.content


def _write_units(
    parsed: ParsedPaper,
    *,
    units_dir: Path,
    encoder: Any,
    chunk_size: int,
) -> list[dict[str, Any]]:
    used_stems: set[str] = set()
    manifest: list[dict[str, Any]] = []
    for unit in parsed.units:
        stem = _unique_stem(f"{unit.kind}-{_safe_id(unit.html_id)}", used_stems)
        body = unit.body if unit.body.endswith("\n") else unit.body + "\n"
        tokens = _count_tokens(encoder, unit.body)
        row: dict[str, Any] = {
            "kind": unit.kind,
            "html_id": unit.html_id,
            "caption": unit.caption,
            "table_number": unit.table_number,
            "tokens": tokens,
            "fits_512": tokens <= chunk_size,
        }
        if unit.kind == "table":
            rel_md = f"units/{stem}.md"
            (units_dir / f"{stem}.md").write_text(body, encoding="utf-8")
            row["md_path"] = rel_md
        else:
            rel_tex = f"units/{stem}.tex"
            (units_dir / f"{stem}.tex").write_text(body, encoding="utf-8")
            row["tex_path"] = rel_tex
            row["tex"] = unit.body
        manifest.append(row)
    return manifest


def _heading_outline(prose: str) -> str:
    lines = [line for line in prose.splitlines() if _MD_HEADING.match(line)]
    return "\n".join(lines) + ("\n" if lines else "")


def _prose_sections(prose: str) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    current_label = Policy.PREAMBLE_SECTION
    current_parts: list[str] = []
    for line in prose.splitlines():
        match = _MD_HEADING.match(line)
        if match:
            if current_parts:
                chunks.append((current_label, "\n".join(current_parts)))
            current_label = match.group(2)
            current_parts = [line]
        else:
            current_parts.append(line)
    if current_parts:
        chunks.append((current_label, "\n".join(current_parts)))
    return chunks


def _safe_id(html_id: str) -> str:
    cleaned = _UNSAFE_ID.sub("_", html_id).strip("._") or "unnamed"
    return cleaned[:120]


def _unique_stem(stem: str, used: set[str]) -> str:
    candidate = stem
    n = 2
    while candidate in used:
        candidate = f"{stem}-{n}"
        n += 1
    used.add(candidate)
    return candidate


def _token_encoder() -> Any:
    import tiktoken

    return tiktoken.get_encoding(Policy.chunk_encoding)


def _count_tokens(encoder: Any, text: str) -> int:
    return len(encoder.encode(text, disallowed_special=()))


def _print_report(
    parsed: ParsedPaper,
    manifest: list[dict[str, Any]],
    encoder: Any,
    chunk_size: int,
) -> None:
    rows: list[tuple[str, str, int, bool]] = []
    for label, body in _prose_sections(parsed.prose_markdown):
        tokens = _count_tokens(encoder, body)
        rows.append(("section", label, tokens, tokens <= chunk_size))
    for unit in manifest:
        rows.append(
            (
                f"unit:{unit['kind']}",
                unit["html_id"],
                int(unit["tokens"]),
                bool(unit["fits_512"]),
            )
        )

    kind_w = max((len(r[0]) for r in rows), default=4)
    id_w = max((len(r[1]) for r in rows), default=2)
    kind_w = max(kind_w, 4)
    id_w = max(id_w, 2)
    print(f"{'kind':<{kind_w}}  {'id':<{id_w}}  {'tokens':>6}  fits_{chunk_size}")
    print(f"{'-' * kind_w}  {'-' * id_w}  {'-' * 6}  --------")
    for kind, html_id, tokens, fits in rows:
        print(
            f"{kind:<{kind_w}}  {html_id:<{id_w}}  {tokens:>6}  "
            f"{'yes' if fits else 'no'}"
        )


if __name__ == "__main__":
    main()
