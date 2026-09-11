import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "ChronoGuard-RAG/1.0 "
    "(research dataset snapshot; respectful crawling)"
)

REQUEST_TIMEOUT = 20


def load_jsonl(path):
    rows = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if line:
                rows.append(json.loads(line))

    return rows


def save_jsonl(rows, path):
    os.makedirs(
        os.path.dirname(path) or ".",
        exist_ok=True,
    )

    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                )
                + "\n"
            )


def normalize_url(url):
    """
    Remove fragments from URLs.

    FreshQA sources often contain Wikipedia text-fragment
    URLs such as:

        https://en.wikipedia.org/wiki/Page#:~:text=...

    The fragment is useful for locating the relevant passage
    manually, but is not sent to the server.
    """

    parsed = urlparse(url)

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            "",
        )
    )


def extract_title(soup):
    if soup.title and soup.title.string:
        return soup.title.string.strip()

    return None


def extract_date_metadata(soup):
    """
    Best-effort extraction of an explicitly published/modified date.

    IMPORTANT:
    A missing date remains None.

    We never invent a date from the download date.
    """

    selectors = [
        ("meta", {"property": "article:published_time"}, "content"),
        ("meta", {"property": "article:modified_time"}, "content"),
        ("meta", {"name": "date"}, "content"),
        ("meta", {"name": "pubdate"}, "content"),
        ("meta", {"itemprop": "datePublished"}, "content"),
        ("meta", {"itemprop": "dateModified"}, "content"),
    ]

    for tag_name, attrs, value_attr in selectors:

        tag = soup.find(
            tag_name,
            attrs=attrs,
        )

        if tag:

            value = tag.get(
                value_attr
            )

            if value:
                return value.strip()

    # Try JSON-LD metadata.
    for script in soup.find_all(
        "script",
        type="application/ld+json",
    ):

        try:
            data = json.loads(
                script.string or ""
            )
        except Exception:
            continue

        objects = (
            data
            if isinstance(data, list)
            else [data]
        )

        for obj in objects:

            if not isinstance(obj, dict):
                continue

            for key in (
                "datePublished",
                "dateModified",
            ):

                value = obj.get(key)

                if value:
                    return str(value).strip()

    return None


def extract_text(soup):
    """
    Extract reasonably clean visible page text.

    Navigation, scripts, styles, and other page chrome are removed.
    """

    for element in soup(
        [
            "script",
            "style",
            "noscript",
            "svg",
            "nav",
            "footer",
            "header",
            "form",
        ]
    ):
        element.decompose()

    main = (
        soup.find("main")
        or soup.find("article")
        or soup.body
    )

    if main is None:
        return ""

    text = main.get_text(
        separator="\n",
        strip=True,
    )

    # Collapse excessive whitespace.
    lines = []

    for line in text.splitlines():

        line = re.sub(
            r"\s+",
            " ",
            line,
        ).strip()

        if line:
            lines.append(line)

    return "\n".join(lines)


def fetch_page(session, url):
    normalized_url = normalize_url(url)

    response = session.get(
        normalized_url,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    text = extract_text(soup)

    if not text:
        raise ValueError(
            "No usable text extracted from page."
        )

    return {
        "requested_url": url,
        "normalized_url": normalized_url,
        "final_url": response.url,
        "title": extract_title(soup),
        "text": text,
        "source_date": extract_date_metadata(soup),
        "http_status": response.status_code,
    }


def collect_unique_urls(question_rows):
    urls = []

    seen = set()

    for row in question_rows:

        for url in row.get(
            "source_urls",
            [],
        ):

            normalized = normalize_url(url)

            if not normalized:
                continue

            if normalized in seen:
                continue

            seen.add(normalized)

            urls.append(
                {
                    "url": url,
                    "normalized_url": normalized,
                }
            )

    return urls


def fetch_sources(
    questions_path,
    output_path,
    delay_seconds=1.0,
    limit=None,
):
    question_rows = load_jsonl(
        questions_path
    )

    urls = collect_unique_urls(
        question_rows
    )

    if limit is not None:
        urls = urls[:limit]

    print(
        f"Unique source URLs: {len(urls)}"
    )

    session = requests.Session()

    session.headers.update(
        {
            "User-Agent": USER_AGENT,
        }
    )

    snapshot_time = datetime.now(
        timezone.utc
    ).isoformat()

    records = []

    successful = 0
    failed = 0

    for position, item in enumerate(urls):

        url = item["url"]

        print(
            f"[{position + 1}/{len(urls)}] "
            f"{url}"
        )

        try:

            page = fetch_page(
                session,
                url,
            )

            record = {
                "doc_id": (
                    f"freshqa_src_{position:06d}"
                ),

                "requested_url": page[
                    "requested_url"
                ],

                "url": page[
                    "normalized_url"
                ],

                "final_url": page[
                    "final_url"
                ],

                "title": page[
                    "title"
                ],

                "text": page[
                    "text"
                ],

                # This is the date extracted from the
                # source page itself, if available.
                "source_date": page[
                    "source_date"
                ],

                # This is NOT evidence date.
                # It only records when we froze the page.
                "snapshot_retrieved_at": snapshot_time,

                "http_status": page[
                    "http_status"
                ],

                "fetch_status": "success",
            }

            records.append(record)

            successful += 1

        except Exception as exc:

            print(
                f"  FAILED: {exc}"
            )

            records.append(
                {
                    "doc_id": (
                        f"freshqa_src_{position:06d}"
                    ),

                    "requested_url": url,

                    "url": item[
                        "normalized_url"
                    ],

                    "final_url": None,

                    "title": None,

                    "text": None,

                    "source_date": None,

                    "snapshot_retrieved_at":
                        snapshot_time,

                    "http_status": None,

                    "fetch_status": "failed",

                    "error": str(exc),
                }
            )

            failed += 1

        # Be polite to source servers.
        if position < len(urls) - 1:
            time.sleep(delay_seconds)

    save_jsonl(
        records,
        output_path,
    )

    print()
    print("Snapshot complete")
    print("-----------------")
    print(f"Successful: {successful}")
    print(f"Failed:     {failed}")
    print(f"Output:     {output_path}")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=(
            "Freeze FreshQA source pages "
            "into a local evidence snapshot."
        )
    )

    parser.add_argument(
        "--questions",
        default=(
            "data/processed/"
            "freshqa_questions.jsonl"
        ),
    )

    parser.add_argument(
        "--output",
        default=(
            "data/raw/"
            "freshqa_evidence_snapshot.jsonl"
        ),
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between requests in seconds.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional URL limit for testing.",
    )

    args = parser.parse_args()

    fetch_sources(
        questions_path=args.questions,
        output_path=args.output,
        delay_seconds=args.delay,
        limit=args.limit,
    )