import argparse
import csv
import json
import os
import re


ANSWER_COLUMNS = [f"answer_{i}" for i in range(10)]


def clean(value):
    """Return a stripped value or None for empty fields."""
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def parse_source_urls(source_value):
    """
    Extract URLs from the FreshQA source field.

    The source column can contain multiple URLs separated by
    HTML <br> tags or whitespace/newlines.
    """

    if not source_value:
        return []

    # Remove HTML line-break tags.
    text = re.sub(
        r"<br\s*/?>",
        "\n",
        str(source_value),
        flags=re.IGNORECASE,
    )

    # Extract URLs.
    urls = re.findall(
        r"https?://[^\s<>]+",
        text,
    )

    cleaned_urls = []

    for url in urls:
        url = url.strip()

        # Remove common trailing punctuation.
        url = url.rstrip(".,;")

        if url and url not in cleaned_urls:
            cleaned_urls.append(url)

    return cleaned_urls


def preprocess(input_path, output_path, split=None, limit=None):
    """
    Convert the actual FreshQA CSV schema into normalized JSONL.

    FreshQA columns handled:

        id
        split
        question
        effective_year
        next_review
        false_premise
        num_hops
        fact_type
        source
        answer_0 ... answer_9
        note
    """

    os.makedirs(
        os.path.dirname(output_path) or ".",
        exist_ok=True,
    )

    cleaned = []
    skipped = 0

    with open(
        input_path,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise ValueError(
                "FreshQA CSV does not contain a header."
            )

        required_columns = {
            "id",
            "split",
            "question",
            "effective_year",
            "next_review",
            "false_premise",
            "num_hops",
            "fact_type",
            "source",
            "answer_0",
            "note",
        }

        missing = (
            required_columns
            - set(reader.fieldnames)
        )

        if missing:
            raise ValueError(
                "FreshQA CSV is missing columns: "
                + ", ".join(sorted(missing))
            )

        for row in reader:

            row_split = clean(row.get("split"))

            # If a split was requested, keep only that split.
            if split is not None:
                if (
                    row_split is None
                    or row_split.upper() != split.upper()
                ):
                    continue

            question = clean(
                row.get("question")
            )

            answer_0 = clean(
                row.get("answer_0")
            )

            if not question or not answer_0:
                skipped += 1
                continue

            # -----------------------------------------------
            # Collect alternative acceptable answers
            # -----------------------------------------------

            aliases = []

            for column in ANSWER_COLUMNS[1:]:

                answer = clean(
                    row.get(column)
                )

                if (
                    answer
                    and answer != answer_0
                    and answer not in aliases
                ):
                    aliases.append(answer)

            # -----------------------------------------------
            # Parse source URLs
            # -----------------------------------------------

            source_urls = parse_source_urls(
                row.get("source")
            )

            # -----------------------------------------------
            # Preserve FreshQA metadata
            # -----------------------------------------------

            record = {
                "query_id": clean(row.get("id")),
                "split": row_split,

                "query": question,

                "gold_answer": answer_0,
                "gold_aliases": aliases,

                "effective_year": clean(
                    row.get("effective_year")
                ),

                "next_review": clean(
                    row.get("next_review")
                ),

                "false_premise": clean(
                    row.get("false_premise")
                ),

                "num_hops": clean(
                    row.get("num_hops")
                ),

                "fact_type": clean(
                    row.get("fact_type")
                ),

                "source_urls": source_urls,

                "note": clean(
                    row.get("note")
                ),
            }

            cleaned.append(record)

            if (
                limit is not None
                and len(cleaned) >= limit
            ):
                break

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as f:

        for record in cleaned:

            f.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                + "\n"
            )

    print(
        f"Processed: {len(cleaned)} examples"
    )

    print(
        f"Skipped:   {skipped}"
    )

    print(
        f"Output:    {output_path}"
    )


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=(
            "Preprocess the actual FreshQA CSV schema."
        )
    )

    parser.add_argument(
        "--input",
        default="data/raw/freshqa.csv",
    )

    parser.add_argument(
        "--output",
        default=(
            "data/processed/"
            "freshqa_questions.jsonl"
        ),
    )

    parser.add_argument(
        "--split",
        default=None,
        help="Optional split, e.g. TEST or DEV.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
    )

    args = parser.parse_args()

    preprocess(
        input_path=args.input,
        output_path=args.output,
        split=args.split,
        limit=args.limit,
    )