"""G1 contract tests only; no adapters, project mutations, staging or commits."""
import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path


def check(schema, value):
    kind = schema["type"]
    types = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool, "null": type(None)}
    if type(value) is not types[kind]:
        raise ValueError("wrong type")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError("invalid enum")
    if kind == "string":
        if len(value) < schema.get("minLength",0) or ("pattern" in schema and re.fullmatch(schema["pattern"],value) is None):
            raise ValueError("invalid string")
    if kind == "integer" and value < schema.get("minimum",0):
        raise ValueError("invalid integer")
    if kind == "array":
        if not schema.get("minItems",0) <= len(value) <= schema.get("maxItems",10**9):
            raise ValueError("invalid array size")
        if schema.get("uniqueItems") and len({json.dumps(x,sort_keys=True) for x in value}) != len(value):
            raise ValueError("duplicate item")
        for item in value:
            check(schema["items"],item)
    if kind == "object":
        properties=schema["properties"]
        if not set(schema["required"]).issubset(value) or set(value)-set(properties):
            raise ValueError("missing or unknown fields")
        for k,v in value.items():
            check(properties[k],v)


def invariants(letter, record):
    if record["execution_status"] != "DRAFT_BLOCKED":
        raise ValueError("no execution authority exists in these examples")
    if letter == "A" and record["aliases"] != record["original_aliases"]:
        raise ValueError("aliases rewritten")
    if letter == "B" and record["body_hashes"][0] != record["body_hashes"][1]:
        raise ValueError("unmatched body")
    if letter in ("C","D"):
        cells=record["conditions"]
        expected={f"{a}/{b}/{c}" for a in ("correct_newer","incorrect_newer")
                  for b in ("neutral","freshness") for c in ("correct_first","incorrect_first")}
        if len(cells)!=8 or set(cells)!=expected:
            raise ValueError("factorial coverage mismatch")
    if letter == "E" and len(record["texts"]) != len(record["metadata_doc_ids"]):
        raise ValueError("candidate metadata mismatch")
    if letter == "F" and record["raw_label"]=="NEEDS_REVIEW" and record["outcome"]!="NEEDS_REVIEW":
        raise ValueError("unresolved label coerced")


def validate(repo):
    package=repo/"docs/consolidation/g1_v1"
    contracts=json.loads((package/"integration_contracts.json").read_text(encoding="utf-8"))
    positives=negatives=0
    for c in contracts["contracts"]:
        for side in ("input","output"):
            check(c[side+"_schema"],c[side+"_example"])
            positives+=1
            broken=dict(c[side+"_example"])
            broken.pop("source_qa_id")
            try:
                check(c[side+"_schema"],broken)
            except ValueError:
                negatives+=1
            else:
                raise AssertionError("missing identity accepted")
        invariants(c["id"],c["output_example"])
        try:
            invariants(c["id"],c["negative_example"])
        except ValueError:
            negatives+=1
        else:
            raise AssertionError("invalid invariant accepted")
    # All writes stay inside this newly allocated OS-temp directory.
    temp=Path(tempfile.mkdtemp(prefix="chronoguard_g1_policy_")).resolve()
    assert temp.parent==Path(tempfile.gettempdir()).resolve()
    def git(*args, data=None):
        result=subprocess.run(["git","-C",str(temp),*args],input=data,capture_output=True,check=True)
        return result.stdout
    git("init","--quiet")
    git("config","core.autocrlf","true")
    baseline=json.loads((package/"baseline_inventory.json").read_text())
    old=(repo/".gitattributes").read_bytes()
    (temp/".gitattributes").write_bytes(old)
    protected=baseline["protected_paths"]
    data=("\n".join(protected)+"\n").encode()
    before=git("check-attr","text","eol","filter","--stdin",data=data)
    (temp/".gitattributes").write_bytes((package/"gitattributes.proposed").read_bytes())
    after=git("check-attr","text","eol","filter","--stdin",data=data)
    assert before==after
    import csv
    with (package/"publication_allowlist.csv").open(encoding="utf-8",newline="") as stream:
        allowed=[r["path"] for r in csv.DictReader(stream) if r["proposed_publication"]=="YES_PROPOSED"]
    roundtripped={}
    objects={}
    for name in allowed:
        original=(repo/name).read_bytes()
        oid=git("hash-object","-w","--path="+name,"--stdin",data=original).decode().strip()
        restored=git("cat-file","--filters","--path="+name,oid)
        assert restored==original,name
        roundtripped[name]=restored
        objects[name]=oid
    # Materialize a Git tree directly: no staged index or commit is needed.
    objects['.gitattributes']=git('hash-object','-w','--stdin',data=(package/'gitattributes.proposed').read_bytes()).decode().strip()
    nested={}
    for name,oid in objects.items():
        parts=name.split('/')
        node=nested
        for part in parts[:-1]:
            node=node.setdefault(part,{})
        node[parts[-1]]=oid
    def make_tree(node):
        lines=[]
        for name,value in sorted(node.items()):
            if isinstance(value,dict):
                lines.append('040000 tree '+make_tree(value)+'\t'+name+'\n')
            else:
                lines.append('100644 blob '+value+'\t'+name+'\n')
        return git('mktree',data=''.join(lines).encode()).decode().strip()
    tree=make_tree(nested)
    git('restore','--source='+tree,'--worktree','--','.')
    for name in allowed:
        assert (temp/name).read_bytes()==(repo/name).read_bytes(),name
    fixtures=[b"LF\nUnicode \xce\xb2\n",b"CRLF\r\n",b"mixed\r\nLF\n"]
    for original in fixtures:
        name="src/eval/synthetic_analysis.py"
        oid=git("hash-object","-w","--path="+name,"--stdin",data=original).decode().strip()
        assert git("cat-file","--filters","--path="+name,oid)==original
    audited=0
    for name,content in roundtripped.items():
        if name.startswith("audits/") and name.endswith("/sha256.json"):
            for child,expected in json.loads(content).items():
                actual=roundtripped[str(Path(name).parent/child).replace("\\","/")]
                assert hashlib.sha256(actual).hexdigest()==expected
                audited+=1
    # No index or commit was necessary: filtering uses only temporary objects.
    assert not (temp/".git/index").exists()
    return {"schema_positive_checks":positives,"schema_negative_checks":negatives,
            "raw_byte_roundtrips":len(allowed),"line_ending_fixture_checks":len(fixtures),
            "tree_checkout_roundtrips":len(allowed),
            "protected_attribute_paths_unchanged":len(protected),"P1_child_hashes_verified_after_roundtrip":audited,
            "temporary_index_created":False,"commits_created":0,"project_files_modified":0,
            "method":"Git filters plus restore from tree object; no staged index or commit",
            "status":"PASS_ENGINEERING_ONLY","scientific_approval":"NONE"}


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--repo",type=Path,required=True)
    print(json.dumps(validate(p.parse_args().repo.resolve()),sort_keys=True))
