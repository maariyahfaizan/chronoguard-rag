# W6-R19 derived evidence identity v1 — Checkpoint 1

Historical scope note (GIT-A2): the status and future-work statements below
describe Checkpoint 1, not the current completion state of later target-index
and recovery work. See [Checkpoint 2B](w6_r19_target_index_2b.md) and the
[development review queue](week6_development_review_queue.md). Neither those
later outputs nor this identity contract certify historical authenticity,
semantic support or final benchmark eligibility. See the
[supervisor review index](supervisor_review/README.md) for the package dependency.

Checkpoint-1 status: identity schema and small in-memory grouping prototype only. This is a
separate derived representation, not a repaired or recertified frozen extraction.
No original shards, Week-4/Week-5 artifacts, failed audit outputs, or original
auditor predicates are changed. No full-corpus transformation has been run.

## Identity contract

Schema: `chronoguard-evidence-identity/v1`. Implementation:
`src/eval/evidence_identity.py`. Functions have no file/network I/O or clock,
randomness, locale, path, or traversal-order dependencies.

### Source occurrences

`SourceOccurrence(artifact_sha256, physical_line)` contains:

| Field | Type | Meaning |
| --- | --- | --- |
| `artifact_sha256` | string, exactly 64 lowercase hexadecimal digits | SHA-256 of the pinned source artifact's exact physical bytes |
| `physical_line` | positive integer; booleans excluded | 1-based physical line in the artifact's uncompressed byte stream |

For gzip, hash the gzip artifact bytes and enumerate lines after decompression.
For plain JSONL, hash and enumerate the plain bytes. Lines are delimited by byte
LF (`0x0a`); include blank lines in numbering and count a final unterminated line.
Do not number parsed/nonblank records, normalize newlines, or count passages
within an original archive row. An original archive row yielding several
passages is not itself a passage occurrence under this two-field schema: use a
pinned passage JSONL artifact, or define a future source-coordinate schema.

Different paths containing byte-identical artifacts identify the same source
occurrences; paths belong in provenance, not identity. Recompression or JSONL
reserialization creates a different artifact identity, even if content variants
are unchanged. Bind equivalent representations through an explicit provenance
mapping; never substitute a decompressed digest for a compressed artifact digest.
The prototype validates digest syntax, not that a caller actually hashed bytes
or supplied the correct physical line. Full-corpus ingestion must verify that.

### Content variants

`EvidenceRecord` is immutable and contains:

| Field | Type | Identity treatment |
| --- | --- | --- |
| `upstream_passage_id` | nonempty Unicode scalar string | Exact value; no ID rewriting |
| `text` | immutable Python `bytes`, including empty or non-UTF-8 bytes | Exact bytes |
| `timestamp` | Unicode scalar string | Validated UTC RFC3339 subset; exact spelling preserved |
| `evidence_fields` | tuple of unique `(name, value)` string pairs | Sorted by name; names nonempty, values may be empty |

All string fields must be strictly UTF-8 encodable: unpaired surrogate code
points are rejected. Field names sort lexicographically by Unicode scalar value,
without locale or normalization. Evidence values are strings only; numbers,
booleans, nulls, nested objects, and implicit coercions are forbidden in v1.

Timestamps must use `YYYY-MM-DDTHH:MM:SS`, optional 1–6 fractional digits, and
`Z` or `+00:00`. Dates/times must exist in the Gregorian calendar, years 1–9999;
leap seconds, naive times, nonzero offsets, and the unknown-offset spelling
`-00:00` are rejected. Equivalent instants with different accepted spellings
remain different variants. This is evidence representation identity, not
equivalence of instants. Validation does not itself establish temporal validity
relative to a question, retention interval, or upstream ID date.

The frozen JSON adapter `record_from_mapping` requires `doc_id`, `text`, and
`timestamp`. `text` is a Unicode scalar string encoded strictly as UTF-8; it is
never stripped, normalized, case-folded, replacement-decoded, or selected by
length. An optional `evidence_fields` string-to-string mapping explicitly
designates additional identity-bearing metadata. Current frozen three-field
records designate no additional fields. Unknown top-level fields are rejected,
not dropped; any future ingestion profile must explicitly enumerate which
metadata becomes evidence fields and which remains occurrence provenance.

The adapter preserves decoded JSON string content, not the original JSON token
spelling (for example, literal `é` and `\u00e9` represent identical text bytes).
It cannot restore invalid UTF-8 bytes already replaced during frozen extraction.
Original artifact bytes and their immutable references remain essential.

### Canonical encoding and SHA-256

The exact preimage is a domain prefix followed by an ASCII JSON array:

```text
occurrence:
  ASCII("chronoguard-evidence-identity/v1") || 00 || ASCII("occurrence") || 00
  || JSON([artifact_sha256, physical_line])

variant:
  ASCII("chronoguard-evidence-identity/v1") || 00 || ASCII("variant") || 00
  || JSON([upstream_passage_id, base64(text), timestamp, sorted_evidence_pairs])
```

Here `00` is one NUL byte, and `||` means byte concatenation. JSON uses the fixed
array positions above, no optional positions, no whitespace, ASCII Unicode
escapes, and no NaN/Infinity. Normative serialization is Python
`json.dumps(payload, ensure_ascii=True, separators=(",", ":"), allow_nan=False)`
encoded as ASCII. Control characters use JSON escapes; non-ASCII BMP scalars
use lowercase `\uXXXX` escapes and non-BMP scalars use surrogate-pair escapes.
`base64(text)` is standard RFC4648 Base64 with padding and no wrapping.
Evidence pairs are JSON two-string arrays, ordered by unique field name.
The test suite pins exact preimage examples for independent implementations.

The IDs are `cgei:v1:occurrence:<lowercase SHA-256 hex>` and
`cgei:v1:variant:<lowercase SHA-256 hex>`. Domain separation prevents reuse across
identity kinds; versioning prevents incompatible schemas sharing a namespace.
Arrays, escaping, and Base64 make the encoding unambiguous, including embedded
NULs, delimiters, newlines, and arbitrary text bytes. SHA-256 is collision
resistant, not mathematically injective. Never assume different preimages cannot
share a digest: grouping compares canonical preimages on variant digest reuse
and raises on a mismatch; occurrence digest reuse checks source coordinates.

## Aliases, duplicates, and multiplicity

`group_occurrences` accepts `(SourceOccurrence, EvidenceRecord)` pairs and
returns sorted immutable `UpstreamAlias` groups. Each upstream ID aliases every
distinct `VariantGroup`; each variant retains its record and all source
coordinates. Alias keys sort by Unicode scalar value, variants by variant ID,
and occurrences by `(artifact_sha256, physical_line)`. Input ordering never
selects a representative text. Nothing is overwritten, merged, or discarded.

- Occurrence multiplicity: count of distinct source occurrences in a variant or
  alias group.
- Exact duplicates under v1: equal designated evidence preimages at different
  source occurrences. An alias's `exact_duplicate_count` is the number of extra
  occurrences, `occurrence_count - len(variants)`, not the count of duplicate
  groups or pairwise duplicate relationships.
- Conflicting variants: more than one distinct variant under the same upstream
  passage ID. This includes differences in text, timestamp, or designated
  metadata; it does not imply semantic contradiction. Duplicates and conflicts
  can coexist within one alias group.

“Exact” here means v1 evidence-field equality, not raw JSONL byte equality. The
prototype does not classify raw-byte duplicates or hash individual raw lines.
Full ingestion must retain those additional observations separately. Repeating
the same source occurrence in the prototype is an ingestion error, even with
the same content; it must not inflate multiplicity. Different upstream IDs or
timestamps always produce distinct variants, even if text bytes are identical.

The prototype is O(number of occurrences plus text bytes) memory and sorts its
output. It is not a streaming/disk-backed 48-million-record implementation or
a proposed retrieval multiplicity policy. It does not validate archive-year,
publication-day, retention, semantic support, complete document membership, or
gold evidence. An upstream document or passage ID is only an alias: **it never
proves exact gold-evidence recovery**. Passage groups cannot safely reconstruct
complete document variants without additional provenance.

Small in-memory usage (the digest must come from the caller's verified artifact):

```python
from src.eval.evidence_identity import (
    SourceOccurrence, record_from_mapping, group_occurrences,
)

aliases = group_occurrences([
    (SourceOccurrence(verified_artifact_sha256, physical_line),
     record_from_mapping(parsed_record)),
])
# aliases[0].variants contains every distinct variant and its source occurrences.
```

## Regression evidence and validation

`tests/fixtures/w6_r19_2008_identity_conflict.json` transcribes the matching local
2008 final passages: same upstream ID ending `_5`, with one omitting
“See the winners and losers of the Wall Street mess here.” It records local
archive lines and the reported canonical extraction lines separately. It is
not an original archive artifact and asserts no digest equivalence with Kaggle.
The regression test creates an explicit two-line in-memory JSONL artifact for
occurrence coordinates; it does not use archive line numbers with a fixture
digest. The test verifies both variants survive without a longest-text rule.

Focused offline tests:

```powershell
python -B -m pytest -q -p no:cacheprovider tests/test_evidence_identity.py tests/test_audit_week6_evidence.py
```

## Future full-corpus release requirements

Before Checkpoint 2, freeze the ingestion metadata profile, compressed/plain
source policy, and handling of already-lost byte information. A full derived
release needs a separate dataset name/version and a manifest pinning schema,
input hashes, original sidecars and failed-audit references, parser commit/file
hashes, transformation code/configuration, decoding policy, dependencies,
retention windows, output serialization/order, and output hashes. Identity
schema version and corpus release version are separate: a new corpus snapshot
need not change v1, but changing preimages, designated-field semantics, accepted
types, or normalization requires a new identity contract/version.

Validate at least:

1. Source artifact hashes and physical line references; malformed records must
   be reported and block certification, not silently skipped.
2. Complete occurrence accounting: sum of variant multiplicities equals valid
   input occurrences, with no missing, invented, or twice-ingested coordinates.
3. All variants retained, aliases complete, digest/preimage consistency checked,
   and raw-byte, evidence-field, metadata, and conflict counts distinguished.
4. Original temporal and provenance checks retained, including UTC publication
   agreement, retention boundaries, and publication before the question.
5. Reproducible IDs and output hashes under independently ordered ingestion;
   source-order dependence limited to the explicitly pinned occurrence lines.
6. Complete-document membership where recoverable; uncertainty explicitly
   retained where only passage shards exist.
7. Gold-resolution statuses distinguishing unique, ambiguous, absent, and
   independently adjudicated evidence; no answer-presence or prefix shortcut.

Retrieval duplicate handling, full document-variant reconstruction, scalable
storage, and gold adjudication remain later decisions. A future derived PASS
certifies its own published contract; the frozen raw audit remains failed.
