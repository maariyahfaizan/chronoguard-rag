import argparse
import json
import os
import random
from collections import defaultdict
from urllib.parse import urlparse


def load_jsonl(path):
    rows = []

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as f:

        for line in f:

            line = line.strip()

            if line:
                rows.append(
                    json.loads(line)
                )

    return rows


def save_jsonl(rows, path):
    os.makedirs(
        os.path.dirname(path) or ".",
        exist_ok=True,
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:

        for row in rows:

            f.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                )
                + "\n"
            )


def normalize_url(url):
    if not url:
        return ""

    parsed = urlparse(
        str(url).strip()
    )

    return (
        f"{parsed.scheme}://"
        f"{parsed.netloc}"
        f"{parsed.path}"
        + (
            f"?{parsed.query}"
            if parsed.query
            else ""
        )
    ).rstrip("/")


def make_candidate_text(doc):
    title = (
        str(doc.get("title") or "")
        .strip()
    )

    text = (
        str(doc.get("text") or "")
        .strip()
    )

    if title:
        return (
            f"Title: {title}\n\n"
            f"{text}"
        )

    return text


def build_url_lookup(evidence_rows):
    lookup = defaultdict(list)

    for doc in evidence_rows:

        if (
            doc.get("fetch_status")
            != "success"
        ):
            continue

        if not doc.get("text"):
            continue

        normalized = normalize_url(
            doc.get("url")
        )

        if not normalized:
            continue

        lookup[normalized].append(doc)

    return lookup


def select_distractors(
    all_documents,
    positive_ids,
    number,
    rng,
):
    candidates = [
        doc
        for doc in all_documents
        if doc.get("doc_id")
        not in positive_ids
    ]

    if len(candidates) <= number:
        return candidates

    return rng.sample(
        candidates,
        number,
    )


def build_pools(
    questions,
    evidence,
    output_path,
    candidates_per_query=20,
    seed=42,
):
    rng = random.Random(seed)

    url_lookup = build_url_lookup(
        evidence
    )

    valid_documents = [
        doc
        for doc in evidence
        if (
            doc.get("fetch_status")
            == "success"
            and doc.get("text")
        )
    ]

    pools = []

    no_source_count = 0
    no_evidence_count = 0

    for question in questions:

        source_urls = question.get(
            "source_urls",
            [],
        )

        source_lookup_keys = {
            normalize_url(url)
            for url in source_urls
            if normalize_url(url)
        }

        positive_documents = []

        for url_key in source_lookup_keys:

            positive_documents.extend(
                url_lookup.get(
                    url_key,
                    [],
                )
            )

        # Deduplicate by document ID.
        positive_by_id = {}

        for doc in positive_documents:
            positive_by_id[
                doc["doc_id"]
            ] = doc

        positive_documents = list(
            positive_by_id.values()
        )

        if not source_urls:
            no_source_count += 1

        if not positive_documents:
            no_evidence_count += 1
            continue

        # If a question has more source documents
        # than the entire candidate pool allows,
        # select deterministically.
        if len(positive_documents) > candidates_per_query:

            positive_documents = rng.sample(
                positive_documents,
                candidates_per_query,
            )

        positive_ids = {
            doc["doc_id"]
            for doc in positive_documents
        }

        remaining = (
            candidates_per_query
            - len(positive_documents)
        )

        distractors = select_distractors(
            valid_documents,
            positive_ids,
            remaining,
            rng,
        )

        selected = (
            positive_documents
            + distractors
        )

        rng.shuffle(selected)

        candidates = []
        metadata = []

        for index, doc in enumerate(
            selected
        ):

            candidates.append(
                make_candidate_text(doc)
            )

            metadata.append(
                {
                    "index": index,
                    "doc_id": doc.get(
                        "doc_id"
                    ),
                    "url": doc.get(
                        "url"
                    ),
                    "final_url": doc.get(
                        "final_url"
                    ),
                    "title": doc.get(
                        "title"
                    ),
                    "source_date": doc.get(
                        "source_date"
                    ),
                    "is_source_document": (
                        doc.get("doc_id")
                        in positive_ids
                    ),
                }
            )

        pool = {
            "query_id": question[
                "query_id"
            ],

            "split": question.get(
                "split"
            ),

            "query": question[
                "query"
            ],

            "gold_answer": question[
                "gold_answer"
            ],

            "gold_aliases": question.get(
                "gold_aliases",
                [],
            ),

            "effective_year": question.get(
                "effective_year"
            ),

            "next_review": question.get(
                "next_review"
            ),

            "false_premise": question.get(
                "false_premise"
            ),

            "num_hops": question.get(
                "num_hops"
            ),

            "fact_type": question.get(
                "fact_type"
            ),

            "note": question.get(
                "note"
            ),

            "source_urls": source_urls,

            "candidates": candidates,

            "candidate_metadata": metadata,

            "pool_config": {
                "candidates_per_query":
                    candidates_per_query,
                "seed": seed,
            },
        }

        pools.append(pool)

    save_jsonl(
        pools,
        output_path,
    )

    print()
    print("Candidate pools")
    print("----------------")
    print(
        f"Questions processed: {len(questions)}"
    )
    print(
        f"Pools created:       {len(pools)}"
    )
    print(
        f"No source URLs:      {no_source_count}"
    )
    print(
        f"No matched evidence: {no_evidence_count}"
    )
    print(
        f"Candidates/query:    {candidates_per_query}"
    )
    print(
        f"Seed:                {seed}"
    )
    print(
        f"Output:              {output_path}"
    )


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=(
            "Build frozen FreshQA "
            "retrieval candidate pools."
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
        "--evidence",
        default=(
            "data/raw/"
            "freshqa_evidence_snapshot.jsonl"
        ),
    )

    parser.add_argument(
        "--output",
        default=(
            "data/processed/"
            "freshqa_control_pools.jsonl"
        ),
    )

    parser.add_argument(
        "--candidates-per-query",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )

    args = parser.parse_args()

    questions = load_jsonl(
        args.questions
    )

    evidence = load_jsonl(
        args.evidence
    )

    build_pools(
        questions=questions,
        evidence=evidence,
        output_path=args.output,
        candidates_per_query=(
            args.candidates_per_query
        ),
        seed=args.seed,
    )