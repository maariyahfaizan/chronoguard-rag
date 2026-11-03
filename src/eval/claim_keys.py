"""Explicit claim contracts; no key generation or approval is performed here."""
from dataclasses import asdict, dataclass, fields
import hashlib
import json


def identity_hash(value):
    """Hash exact JSON identity, preserving alias order and original text."""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ClaimContext:
    question_id: str
    question: str
    primary_gold: str
    aliases: tuple[str, ...]
    source_id: str
    source_text: str

    def validate_types(self):
        validate_record(self, {"aliases"})


@dataclass(frozen=True)
class ClaimKey:
    key_id: str
    question_id: str
    question_hash: str
    primary_gold_hash: str
    aliases_hash: str
    source_id: str
    source_hash: str
    subject: str
    relation: str
    false_state: str
    units: str | None
    polarity: str
    temporal_qualifiers: tuple[str, ...]
    false_expressions: tuple[str, ...]
    gold_expressions: tuple[str, ...]
    provenance: str
    approval_status: str
    reviewer: str
    schema_version: str = "claim_key_v2"
    ambiguous: bool = False

    def validate_types(self):
        validate_record(self, {"temporal_qualifiers", "false_expressions", "gold_expressions"})

    @property
    def digest(self):
        self.validate_types()
        return identity_hash(asdict(self))

    def problems(self, context, approved_keys):
        from .claim_matching_v2 import expression_normalize as normalize
        self.validate_types()
        context.validate_types()
        errors = []
        bindings = {
            "question_id": context.question_id,
            "question_hash": identity_hash(context.question),
            "primary_gold_hash": identity_hash(context.primary_gold),
            "aliases_hash": identity_hash(context.aliases),
            "source_id": context.source_id,
            "source_hash": identity_hash(context.source_text),
        }
        errors.extend("mismatch:" + k for k, v in bindings.items() if getattr(self, k) != v)
        if self.schema_version != "claim_key_v2":
            errors.append("unsupported_key_schema")
        if (self.approval_status != "approved" or not self.reviewer.strip()
                or approved_keys.get(self.key_id) != self.digest):
            errors.append("unapproved_or_stale_key")
        if self.ambiguous:
            errors.append("ambiguous_key")
        if not all(str(x).strip() for x in (self.key_id, self.subject, self.relation,
                                           self.false_state, self.provenance,
                                           context.question_id, context.source_id)):
            errors.append("incomplete_key")
        if self.polarity not in ("positive", "negative"):
            errors.append("invalid_polarity")
        false = {normalize(x) for x in self.false_expressions}
        gold = {normalize(x) for x in self.gold_expressions}
        if not false or not gold or "" in false | gold or None in false | gold:
            errors.append("missing_expressions")
        if false & (gold | {normalize(context.primary_gold)}
                    | {normalize(x) for x in context.aliases}):
            errors.append("alias_or_gold_collision")
        # Every accepted full expression, including short answers, is part of the
        # reviewed digest. No substrings, regexes, or answer-derived keys exist.
        return errors


def validate_record(record, tuple_fields):
    """Reject malformed runtime values; frozen records require immutable members."""
    for field in fields(record):
        value = getattr(record, field.name)
        if field.name in tuple_fields:
            if type(value) is not tuple or any(type(x) is not str or not x.strip() for x in value):
                raise ValueError("invalid tuple field:" + field.name)
        elif field.name == "ambiguous":
            if type(value) is not bool:
                raise ValueError("invalid boolean field:ambiguous")
        elif field.name == "units" and value is None:
            continue
        elif type(value) is not str or not value.strip():
            raise ValueError("invalid string field:" + field.name)
