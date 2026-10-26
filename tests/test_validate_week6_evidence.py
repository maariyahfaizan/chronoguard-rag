import gzip
import json
from datetime import datetime, timezone
from scripts.validate_week6_evidence import audit


def test_gold_parent_recovery_and_conflict(tmp_path):
    parent = '20100210000000000000\x00\x01abc\x00\x01'
    meta = tmp_path / 'meta.jsonl'
    meta.write_text(json.dumps({'qa_id': 'eval-x', 'recent_or_past': 'past',
        'evidence_id': parent, 'evidence_ts': int(datetime(2010, 2, 10, 8, tzinfo=timezone.utc).timestamp()),
        'window_start': '2010-02-01T00:00:00+00:00', 'window_end': '2010-02-20T00:00:00+00:00',
        'answers': ['$746 million']}) + '\n')
    shard = tmp_path / '2010.jsonl.gz'
    with gzip.open(shard, 'wt', encoding='utf-8') as f:
        for suffix, text in [('_0', 'Other'), ('_1', 'Sales $746 million')]:
            f.write(json.dumps({'doc_id': parent + suffix, 'text': text,
                                'timestamp': '2010-02-10T00:00:00+00:00'}) + '\n')
    rows = audit(meta, shard, 2010)
    assert len(rows) == 1
    assert rows[0]['passage_count'] == 2
    assert rows[0]['answer_string_hits'] == ['$746 million']
    assert rows[0]['status'] == 'candidate_for_semantic_review'
    with gzip.open(shard, 'at', encoding='utf-8') as f:
        f.write(json.dumps({'doc_id': parent + '_1', 'text': 'conflicting',
                            'timestamp': '2010-02-10T00:00:00+00:00'}) + '\n')
    rows = audit(meta, shard, 2010)
    assert rows[0]['conflicting_passage_ids'] == [parent + '_1']
    assert rows[0]['status'] == 'needs_review'

def test_answer_matching_ignores_trailing_punctuation():
    from scripts.validate_week6_evidence import (
        answer_appears_in_evidence,
    )

    evidence = (
        "Woods, sidelined by back pain for the past "
        "15 months, will launch his comeback."
    )

    assert answer_appears_in_evidence("Back pain. ", evidence)
    assert answer_appears_in_evidence(
        "Sidelined by back pain.", evidence
    )
    assert not answer_appears_in_evidence(
        "Knee injury", evidence
    )
