import gzip
import json
from pathlib import Path

import pytest

from scripts.export_week6_candidate_metadata import export


def test_export(tmp_path):
    raw = tmp_path / 'raw.jsonl.gz'
    win = tmp_path / 'windows.jsonl'
    out = tmp_path / 'metadata.jsonl'
    record = {'qa_id':'eval-1','question':'Q?','answers':['A'], 'question_ts':20,
              'evidence_id':'doc','evidence_ts':10,'recent_or_past':'past'}
    with gzip.open(raw,'wt') as f:
        f.write(json.dumps(record)+'\n')
    win.write_text(json.dumps({k:record[k] for k in ('qa_id','evidence_id','evidence_ts','recent_or_past')})+'\n')
    assert export(raw,win,out)==1
    assert json.loads(out.read_text())['answers']==['A']
    with pytest.raises(FileExistsError):
        export(raw,win,out)


def test_reject_mismatch(tmp_path):
    raw=tmp_path/'raw.jsonl'; win=tmp_path/'win.jsonl'
    raw.write_text(json.dumps({'qa_id':'q','evidence_id':'other'})+'\n')
    win.write_text(json.dumps({'qa_id':'q','evidence_id':'doc'})+'\n')
    with pytest.raises(ValueError, match='evidence_id'):
        export(raw,win,tmp_path/'out.jsonl')
