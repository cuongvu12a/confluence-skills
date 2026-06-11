#!/usr/bin/env python3
"""
Confluence Page Fetcher — Middleware for AI agents.

Fetches Confluence pages using PAT authentication and outputs markdown.
Auto-installs dependencies on first run.

Usage:
  python confluence_fetch.py --url "https://confluence.mymerchize.com/pages/viewpage.action?pageId=12345"
  python confluence_fetch.py --page-id 12345
  python confluence_fetch.py --page-id 12345 --children
  python confluence_fetch.py --page-id 12345 --output page.md
  python confluence_fetch.py --search 'title ~ "feature name" AND space = "ERP"'

Environment variables:
  CONFLUENCE_BASE_URL  Base URL (default: https://confluence.mymerchize.com)
  CONFLUENCE_PAT       Personal Access Token
"""

import json
import os
import re
import subprocess
import sys
from urllib.parse import parse_qs, urlparse

DEFAULT_BASE_URL = "https://confluence.mymerchize.com"
REQUIRED_PACKAGES = ["requests", "markdownify", "beautifulsoup4"]


# ---------------------------------------------------------------------------
# Auto-install dependencies
# ---------------------------------------------------------------------------

def _ensure_deps():
    missing = []
    for pkg in REQUIRED_PACKAGES:
        import_name = "bs4" if pkg == "beautifulsoup4" else pkg.replace("-", "_")
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"[confluence_fetch] Installing: {', '.join(missing)}", file=sys.stderr)
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + missing,
            stdout=subprocess.DEVNULL,
        )
        print("[confluence_fetch] Done.", file=sys.stderr)


_ensure_deps()

import requests  # noqa: E402 (after auto-install)
from bs4 import BeautifulSoup  # noqa: E402
from markdownify import markdownify as md  # noqa: E402


# ---------------------------------------------------------------------------
# Confluence HTML → Markdown
# ---------------------------------------------------------------------------

def _preprocess_confluence_html(html: str) -> str:
    """
    Clean Confluence-specific markup before markdown conversion.
    Handles ac:structured-macro, ac:rich-text-body, and other Confluence tags.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Code blocks: <ac:structured-macro ac:name="code">
    for macro in soup.find_all("ac:structured-macro", {"ac:name": "code"}):
        lang_param = macro.find("ac:parameter", {"ac:name": "language"})
        lang = lang_param.get_text(strip=True) if lang_param else ""
        body = macro.find("ac:plain-text-body")
        code_text = body.get_text() if body else ""
        new_tag = soup.new_tag("pre")
        code_tag = soup.new_tag("code", attrs={"class": f"language-{lang}"} if lang else {})
        code_tag.string = code_text
        new_tag.append(code_tag)
        macro.replace_with(new_tag)

    # Info / Note / Warning panels → blockquote
    for panel_name in ("info", "note", "warning", "tip"):
        for macro in soup.find_all("ac:structured-macro", {"ac:name": panel_name}):
            body = macro.find("ac:rich-text-body")
            inner = body.decode_contents() if body else ""
            bq = BeautifulSoup(f"<blockquote><strong>[{panel_name.upper()}]</strong> {inner}</blockquote>", "html.parser")
            macro.replace_with(bq)

    # Expand macro (collapsible sections) → heading + content
    for macro in soup.find_all("ac:structured-macro", {"ac:name": "expand"}):
        title_param = macro.find("ac:parameter", {"ac:name": "title"})
        title = title_param.get_text(strip=True) if title_param else "Details"
        body = macro.find("ac:rich-text-body")
        inner = body.decode_contents() if body else ""
        replacement = BeautifulSoup(f"<h4>{title}</h4>{inner}", "html.parser")
        macro.replace_with(replacement)

    # Remove remaining unknown ac: tags but keep their inner rich-text-body content
    for macro in soup.find_all("ac:structured-macro"):
        body = macro.find("ac:rich-text-body")
        if body:
            macro.replace_with(body)
        else:
            macro.decompose()

    # ac:link → plain text with page title
    for link in soup.find_all("ac:link"):
        page_title = link.find("ri:page")
        text = page_title.get("ri:content-title", "") if page_title else link.get_text(strip=True)
        link.replace_with(text)

    # Remove ac:image, ac:emoticon, etc.
    for tag in soup.find_all(re.compile(r"^ac:")):
        tag.decompose()
    for tag in soup.find_all(re.compile(r"^ri:")):
        tag.decompose()

    return str(soup)


def html_to_markdown(html: str) -> str:
    """Convert Confluence HTML body to clean Markdown."""
    cleaned = _preprocess_confluence_html(html)
    result = md(
        cleaned,
        heading_style="ATX",       # # H1, ## H2
        bullets="-",
        code_language_callback=lambda el: el.get("class", [""])[0].replace("language-", "") if el.get("class") else "",
        strip=["script", "style"],
        newline_style="backslash",
    )
    # Collapse 3+ blank lines into 2
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _get(url: str, pat: str) -> dict:
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {pat}", "Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_page(base_url: str, page_id: str, pat: str) -> dict:
    url = (
        f"{base_url.rstrip('/')}/rest/api/content/{page_id}"
        "?expand=body.storage,ancestors,metadata.labels,version,space,children.page"
    )
    return _get(url, pat)


def fetch_children(base_url: str, page_id: str, pat: str) -> list:
    url = f"{base_url.rstrip('/')}/rest/api/content/{page_id}/child/page?limit=50"
    return _get(url, pat).get("results", [])


def search_pages(base_url: str, cql: str, pat: str, limit: int = 10) -> list:
    import urllib.parse
    url = f"{base_url.rstrip('/')}/rest/api/content/search?cql={urllib.parse.quote(cql)}&limit={limit}"
    return _get(url, pat).get("results", [])


def extract_page_id(url_or_id: str) -> str:
    if url_or_id.isdigit():
        return url_or_id
    parsed = urlparse(url_or_id)
    params = parse_qs(parsed.query)
    if "pageId" in params:
        return params["pageId"][0]
    match = re.search(r"/pages/(\d+)", parsed.path)
    if match:
        return match.group(1)
    raise ValueError(f"Cannot extract page ID from: {url_or_id}")


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_page(page: dict, base_url: str, include_body: bool = True) -> str:
    title = page.get("title", "Unknown")
    page_id = page.get("id", "")
    space_key = page.get("space", {}).get("key", "")
    version = page.get("version", {}).get("number", "")
    page_url = f"{base_url.rstrip('/')}/pages/viewpage.action?pageId={page_id}"

    lines = [
        f"# {title}",
        "",
        f"**Page ID**: {page_id}  ",
        f"**Space**: {space_key}  ",
        f"**Version**: {version}  ",
        f"**URL**: {page_url}",
        "",
    ]

    labels = page.get("metadata", {}).get("labels", {}).get("results", [])
    if labels:
        lines.append(f"**Labels**: {', '.join(l.get('name', '') for l in labels)}")
        lines.append("")

    ancestors = page.get("ancestors", [])
    if ancestors:
        breadcrumb = " > ".join(a.get("title", "") for a in ancestors)
        lines.append(f"**Path**: {breadcrumb} > {title}")
        lines.append("")

    lines += ["---", ""]

    if include_body:
        html = page.get("body", {}).get("storage", {}).get("value", "")
        lines.append(html_to_markdown(html) if html else "*(No content)*")

    children = page.get("children", {}).get("page", {}).get("results", [])
    if children:
        lines += ["", "## Child Pages"]
        for c in children:
            cid = c.get("id", "")
            ctitle = c.get("title", "")
            curl = f"{base_url.rstrip('/')}/pages/viewpage.action?pageId={cid}"
            lines.append(f"- [{ctitle}]({curl}) (ID: {cid})")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Fetch Confluence pages as Markdown for AI agents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="Full Confluence page URL")
    group.add_argument("--page-id", metavar="ID", help="Confluence page ID")
    group.add_argument("--search", metavar="CQL", help='CQL query, e.g. \'title ~ "feature" AND space = "ERP"\'')

    parser.add_argument("--base-url", default=os.environ.get("CONFLUENCE_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--token", default=os.environ.get("CONFLUENCE_PAT"), help="Personal Access Token")
    parser.add_argument("--children", action="store_true", help="Also fetch child pages")
    parser.add_argument("--no-body", action="store_true", help="Output metadata only")
    parser.add_argument("--output", "-o", help="Save to file (default: stdout)")
    parser.add_argument("--json", action="store_true", dest="raw_json", help="Output raw JSON")
    parser.add_argument("--search-limit", type=int, default=10)

    args = parser.parse_args()

    if not args.token:
        sys.exit("Error: PAT token required. Set CONFLUENCE_PAT env var or use --token.")

    base_url = args.base_url
    pat = args.token

    if args.search:
        results = search_pages(base_url, args.search, pat, args.search_limit)
        if args.raw_json:
            output = json.dumps(results, indent=2, ensure_ascii=False)
        else:
            lines = [f"# Search: {args.search}", ""]
            for r in results:
                rid, rtitle = r.get("id", ""), r.get("title", "")
                rurl = f"{base_url.rstrip('/')}/pages/viewpage.action?pageId={rid}"
                lines.append(f"- **[{rtitle}]({rurl})** (ID: {rid})")
            output = "\n".join(lines)
    else:
        page_id = extract_page_id(args.url) if args.url else args.page_id
        page = fetch_page(base_url, page_id, pat)

        if args.raw_json:
            output = json.dumps(page, indent=2, ensure_ascii=False)
        else:
            parts = [format_page(page, base_url, include_body=not args.no_body)]
            if args.children:
                for child in fetch_children(base_url, page_id, pat):
                    cid = child.get("id", "")
                    try:
                        cp = fetch_page(base_url, cid, pat)
                        parts.append("\n\n---\n\n" + format_page(cp, base_url, include_body=not args.no_body))
                    except Exception as e:
                        parts.append(f"\n\n*(Error fetching child {cid}: {e})*")
            output = "".join(parts)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Saved to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
