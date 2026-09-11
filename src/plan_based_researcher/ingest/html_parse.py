"""In-memory arXiv HTML parser: bytes → units and residual markdown (PARSE-01–03)."""

from __future__ import annotations

import re
from copy import copy
from dataclasses import dataclass
from typing import Any, Literal

from bs4 import BeautifulSoup, NavigableString, Tag

from plan_based_researcher.ingest.labels import table_number_for

__all__ = ["ParsedPaper", "ParsedUnit", "parse_arxiv_html"]

_ARTICLE_ROOT = (
    "section.ltx_section, div.ltx_page_content, article.ltx_document, "
    "div.ltx_document, div.ltx_page_main"
)
_DISPLAYSTYLE = re.compile(r"\\displaystyle\s*")
_EQUATION_CLASSES = frozenset({"ltx_equation", "ltx_equationgroup"})
_ZERO_WIDTH_RULE = re.compile(r"width\s*:\s*0(\.0)?pt", re.I)
_END_MATTER_HEADING = re.compile(
    r"^(?:(?:\d+(?:\.\d+)*|[IVXLCM]+)\.?\s+)?"
    r"(?:acknowledgements?|acknowledgments?|contributors?)$",
    re.I,
)


@dataclass(frozen=True, slots=True)
class ParsedUnit:
    kind: Literal["table", "equation"]
    html_id: str
    caption: str
    table_number: str
    body: str


@dataclass(frozen=True, slots=True)
class ParsedPaper:
    usable: bool
    prose_markdown: str
    units: list[ParsedUnit]
    reason: str


def parse_arxiv_html(html_bytes: bytes) -> ParsedPaper:
    soup = BeautifulSoup(html_bytes, "lxml")
    if soup.select_one(_ARTICLE_ROOT) is None:
        return ParsedPaper(
            usable=False,
            prose_markdown="",
            units=[],
            reason="no article root",
        )

    generated = 0
    table_index = 0
    units: list[ParsedUnit] = []

    def html_id_for(*nodes: Tag | None) -> str:
        nonlocal generated
        for node in nodes:
            if node is None:
                continue
            raw = (node.get("id") or "").strip()
            if raw:
                return str(raw)
        generated += 1
        return f"unit-{generated:04d}"

    def append_table(*, tag_root: Tag, html_id: str, caption: str, body: str) -> None:
        nonlocal table_index
        table_index += 1
        units.append(
            ParsedUnit(
                kind="table",
                html_id=html_id,
                caption=caption,
                table_number=table_number_for(
                    tag=_ltx_tag_text(tag_root),
                    caption=caption,
                    index_among_tables=table_index,
                ),
                body=body,
            )
        )

    for figure in list(soup.select("figure.ltx_table")):
        if not isinstance(figure, Tag):
            continue
        inner = figure.find("table", class_="ltx_tabular")
        inner_table = inner if isinstance(inner, Tag) else None
        html_id = html_id_for(figure, inner_table)
        body_node = inner_table if inner_table is not None else figure
        caption = _caption_text(figure)
        append_table(
            tag_root=figure,
            html_id=html_id,
            caption=caption,
            body=_table_to_markdown(body_node),
        )
        _replace_with_placeholder(soup, figure, "table", html_id)

    for figure in list(soup.select("figure.ltx_figure")):
        if not isinstance(figure, Tag):
            continue
        figure.replace_with(NavigableString(_caption_text(figure)))

    for table in list(soup.find_all("table")):
        if _is_layout_only_table(table):
            table.decompose()

    for node in list(soup.find_all("table")):
        if not isinstance(node, Tag) or node.parent is None:
            continue
        kind = _table_kind(node)
        html_id = html_id_for(node)
        if kind == "equation":
            units.append(
                ParsedUnit(
                    kind="equation",
                    html_id=html_id,
                    caption=_equation_caption(node),
                    table_number="",
                    body=_equation_tex(node),
                )
            )
        else:
            append_table(
                tag_root=node,
                html_id=html_id,
                caption=_caption_text(node),
                body=_table_to_markdown(node),
            )
        _replace_with_placeholder(soup, node, kind, html_id)

    _drop_bibliography(soup)
    _drop_frontmatter(soup)
    convert_root = (
        soup.select_one("article.ltx_document")
        or soup.select_one("div.ltx_page_content")
        or soup.body
        or soup
    )
    _rewrite_inline_math(convert_root)
    prose = _html_to_markdown(convert_root)
    if not prose.strip() and not units:
        return ParsedPaper(
            usable=False,
            prose_markdown=prose,
            units=[],
            reason="empty prose and no units",
        )
    return ParsedPaper(
        usable=True,
        prose_markdown=prose,
        units=units,
        reason="",
    )


def _replace_with_placeholder(soup: Any, node: Any, kind: str, html_id: str) -> None:
    placeholder = soup.new_tag("p")
    placeholder.string = f"[{kind.upper()}:{html_id}]"
    node.replace_with(placeholder)


def _table_kind(node: Any) -> Literal["table", "equation"]:
    classes = set(node.get("class") or [])
    if classes & _EQUATION_CLASSES:
        return "equation"
    if "ltx_eqn_table" in classes and "ltx_tabular" not in classes:
        return "equation"
    return "table"


def _ltx_tag_text(node: Any) -> str:
    tag = node.find(class_="ltx_tag") if hasattr(node, "find") else None
    if tag is None:
        return ""
    return tag.get_text(" ", strip=True)


def _equation_caption(node: Any) -> str:
    tag = node.find(class_="ltx_tag_equation") if hasattr(node, "find") else None
    if tag is None:
        return ""
    return tag.get_text(" ", strip=True)


def _drop_bibliography(root: Any) -> None:
    """Remove the paper bibliography so it is not converted to markdown.

    In-text cites such as [5, 2] stay in the body. The References list itself
    is not useful for retrieve: it duplicates metadata and pollutes chunks.
    """
    if not hasattr(root, "select"):
        return
    for node in list(root.select("section.ltx_bibliography, ul.ltx_biblist")):
        node.decompose()


def _drop_frontmatter(root: Any) -> None:
    """Remove author/thanks/email blocks and end-matter people lists.

    Author names already live on the arXiv metadata. Body footnotes outside
    ``div.ltx_authors`` are kept. Scientific ``Contributions`` sections stay.
    """
    if not hasattr(root, "select"):
        return
    for node in list(root.select("div.ltx_authors, section.ltx_acknowledgements")):
        node.decompose()
    _drop_end_matter_heading_sections(root)


def _drop_end_matter_heading_sections(root: Any) -> None:
    if not hasattr(root, "find_all"):
        return
    heading_names = ["h1", "h2", "h3", "h4", "h5", "h6"]
    for heading in list(root.find_all(heading_names)):
        if not isinstance(heading, Tag):
            continue
        title = " ".join(heading.get_text(" ", strip=True).split())
        if not _END_MATTER_HEADING.fullmatch(title):
            continue
        section = heading.find_parent("section")
        if (
            isinstance(section, Tag)
            and heading is section.find(heading_names)
        ):
            section.decompose()
        else:
            heading.decompose()


def _is_layout_only_table(table: Any) -> bool:
    """True if this is a LaTeXML spacer tabular, not a real table.

    LaTeX vertical space often becomes a one-cell ``ltx_tabular`` whose only
    child is a ``span.ltx_rule`` with ``width: 0pt``. Those must not be
    extracted as table units.
    """
    if getattr(table, "name", None) != "table":
        return False
    classes = table.get("class") or []
    if "ltx_tabular" not in classes:
        return False

    clone = copy(table)
    for rule in clone.select("span.ltx_rule"):
        rule.decompose()
    if clone.get_text(strip=True):
        return False

    rules = table.select("span.ltx_rule")
    if not rules:
        return False
    return all(_ZERO_WIDTH_RULE.search(rule.get("style") or "") for rule in rules)


def _caption_text(root: Any) -> str:
    node = root.find("figcaption") if hasattr(root, "find") else None
    if node is None and hasattr(root, "find"):
        node = root.find(class_="ltx_caption")
    if not isinstance(node, Tag):
        return ""
    return node.get_text(" ", strip=True)


def _math_tex(node: Any) -> str:
    if not isinstance(node, Tag):
        return ""
    annotation = node.find("annotation", attrs={"encoding": "application/x-tex"})
    raw = annotation.get_text() if annotation is not None else ""
    if not raw.strip() and node.name == "math":
        raw = node.get("alttext") or ""
    return _DISPLAYSTYLE.sub("", raw).strip()


def _equation_tex(node: Any) -> str:
    parts: list[str] = []
    maths = node.find_all("math") if hasattr(node, "find_all") else []
    for math in maths:
        tex = _math_tex(math)
        if tex:
            parts.append(tex)
    if not parts:
        tex = _math_tex(node)
        if tex:
            parts.append(tex)
    if not parts:
        return ""
    return "$$\n" + "\n".join(parts) + "\n$$"


def _rewrite_inline_math(root: Any) -> None:
    if not hasattr(root, "find_all"):
        return
    for math in list(root.find_all("math", class_="ltx_Math")):
        if not isinstance(math, Tag):
            continue
        tex = _math_tex(math)
        math.replace_with(NavigableString(f"${tex}$" if tex else ""))


def _table_to_markdown(node: Any) -> str:
    for rule in node.select("span.ltx_rule"):
        rule.decompose()
    _rewrite_inline_math(node)
    markdown = _html_to_markdown(node).strip()
    return markdown + "\n" if markdown else ""


def _html_to_markdown(root: Any) -> str:
    from markdownify import MarkdownConverter

    class ArxivHtmlConverter(MarkdownConverter):
        def convert_cite(self, el, text, parent_tags):
            labels = [
                a.get_text(" ", strip=True)
                for a in el.find_all("a")
                if a.get_text(" ", strip=True)
            ]
            if labels:
                return "[" + ", ".join(labels) + "]"
            return (text or "").strip()

    return ArxivHtmlConverter(
        heading_style="ATX",
        wrap=False,
        bs4_options="lxml",
        strip=["script", "style", "nav"],
        escape_underscores=False,
        table_infer_header=True,
    ).convert_soup(root)
