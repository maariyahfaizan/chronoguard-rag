#!/usr/bin/env python3
"""CPU-only, read-only Week 4 post-hoc evaluation from the frozen transfer ZIP."""
import argparse, csv, hashlib, json, zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

SYSTEMS = ('e1','e2','e3','e4')

def load_jsonl(z, path):
    return [json.loads(x) for x in z.read(path).splitlines() if x.strip()]

def write_csv(path, rows, fields):
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        w=csv.DictWriter(f, fieldnames=fields, extrasaction='ignore');w.writeheader();w.writerows(rows)

def publication_utc(raw):
    if not raw: return None
    try:
        return datetime.fromisoformat(str(raw).replace('Z','+00:00')).astimezone(timezone.utc).date()
    except (ValueError,TypeError): return None

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--zip', required=True, type=Path);ap.add_argument('--out', required=True, type=Path)
    args=ap.parse_args()
    if not args.zip.is_file(): raise SystemExit('Transfer ZIP missing: '+str(args.zip))
    if args.out.exists(): raise SystemExit('Output directory already exists; refusing overwrite: '+str(args.out))
    args.out.mkdir(parents=True)
    digest=hashlib.sha256(args.zip.read_bytes()).hexdigest()
    base='results/week4_v2/week4_v2_{}_full_002/answers.jsonl'
    with zipfile.ZipFile(args.zip) as z:
        pools=load_jsonl(z,'data/processed/week4_v2/a15_full_roundtrip_v1/pool.jsonl')
        assert len(pools)==100, 'Expected exactly 100 frozen questions'
        frames={p['frame_id'] for p in pools}
        orders={p['question_order']:p for p in pools}
        runs={s:load_jsonl(z,base.format(s)) for s in SYSTEMS}
    for s,records in runs.items():
        assert len(records)==100, (s,len(records))
    # The run embeds its original frozen frame; join by frame_id, not by file order.
    retrieval=[]; queue={}; stats=[]; exposure_by_question=defaultdict(dict)
    for system, records in runs.items():
        seen=set(); future=0; known=0; unknown=0; affected=0; counts=Counter()
        for answer in records:
            envelope=answer['source_envelope']; frame_id=envelope['frame_id']
            assert frame_id in frames, 'Run frame absent from frozen pool'
            order=envelope['question_order']
            assert order not in seen, 'Repeated question order in run'
            seen.add(order)
            frozen=orders[order]['record']; embedded=envelope['record']
            assert frozen['canonical_question_id']==embedded['canonical_question_id'], 'Question identity mismatch'
            candidates={c['child_occurrence_id']:c for c in frozen['candidates']}
            top=answer['retrieved']
            assert len(top)==5, 'Expected exactly 5 retrieved children'
            assert len(set(x['child_occurrence_id'] for x in top))==5, 'Duplicate top-5 occurrence'
            qtime=frozen['original_qa_record'].get('question_ts')
            qdate=datetime.fromtimestamp(int(qtime),timezone.utc).date() if qtime is not None else None
            qfuture=0
            for rank, hit in enumerate(top,1):
                cid=hit['child_occurrence_id']; assert cid in candidates, 'Retrieved child missing from pool'
                child=candidates[cid]
                # Raw preserved publication timestamp; never interpret this as authenticated chronology.
                pub=child['publication_time']['raw_value']
                pdate=publication_utc(pub)
                flag='FUTURE' if pdate and qdate and pdate>qdate else ('PAST_OR_SAME_DAY' if pdate and qdate else 'UNKNOWN')
                if flag=='FUTURE': future+=1;qfuture+=1
                if flag=='UNKNOWN': unknown+=1
                else: known+=1
                counts[flag]+=1
                retrieval.append({'system':system.upper(),'question_id':frozen['question_id'],'question_order':frozen['question_order'],'rank':rank,'child_occurrence_id':cid,'score':hit.get('score'),'question_utc_date':str(qdate) if qdate else '', 'publication_utc_date':str(pdate) if pdate else '', 'timestamp_chronology':flag})
                key=(frozen['canonical_question_id'],cid)
                if key not in queue:
                    queue[key]={'question_id':frozen['question_id'],'question_order':frozen['question_order'],'canonical_question_id':frozen['canonical_question_id'],'question':frozen['original_question'],'gold_aliases_unreviewed':' | '.join(map(str,frozen['gold_aliases'])),'child_occurrence_id':cid,'canonical_child_id':child['canonical_child_id'],'child_text':child['child_text'],'question_utc_date':str(qdate) if qdate else '', 'publication_utc_date':str(pdate) if pdate else '', 'timestamp_chronology':flag,'systems':'','ranks':'','human_relevance_label':'','reviewer_notes':''}
                queue[key]['systems']+=(';' if queue[key]['systems'] else '')+system.upper()
                queue[key]['ranks']+=(';' if queue[key]['ranks'] else '')+str(rank)
            if qfuture: affected+=1
            exposure_by_question[frozen['question_id']][system.upper()]=qfuture
        assert len(seen)==100
        stats.append({'system':system.upper(),'questions':len(seen),'top5_slots':len(seen)*5,'future_slots':future,'future_slot_rate':round(future/(len(seen)*5),6),'questions_with_future_top5':affected,'question_exposure_rate':round(affected/len(seen),6),'unknown_timestamp_slots':unknown,'parseable_timestamp_slots':known})
    queue_rows=sorted(queue.values(),key=lambda x:(int(x['question_order']),x['child_occurrence_id']))
    # Bounded 100-item pilot: include all future-dated unique pairs, then
    # prioritize cross-system overlap while spreading remaining items over questions.
    future_rows=[r for r in queue_rows if r['timestamp_chronology']=='FUTURE']
    other_rows=[r for r in queue_rows if r['timestamp_chronology']!='FUTURE']
    other_rows.sort(key=lambda r:(-len(r['systems'].split(';')),int(r['question_order']),r['child_occurrence_id']))
    pilot=list(future_rows); picked_questions={r['question_id'] for r in pilot}
    for row in other_rows:
        if len(pilot)>=100: break
        if row['question_id'] not in picked_questions:
            pilot.append(row);picked_questions.add(row['question_id'])
    if len(pilot)<100:
        picked={(r['canonical_question_id'],r['child_occurrence_id']) for r in pilot}
        for row in other_rows:
            if len(pilot)>=100: break
            if (row['canonical_question_id'],row['child_occurrence_id']) not in picked:
                pilot.append(row)
    pilot.sort(key=lambda r:(int(r['question_order']),r['child_occurrence_id']))
    write_csv(args.out/'bounded_100_item_annotation_pilot.csv',pilot,list(queue_rows[0]))
    retrieval.sort(key=lambda x:(x['system'],int(x['question_order']),int(x['rank'])))
    write_csv(args.out/'temporal_exposure_by_system.csv',stats,list(stats[0]))
    write_csv(args.out/'top5_retrieval_chronology.csv',retrieval,list(retrieval[0]))
    write_csv(args.out/'pooled_top5_relevance_queue.csv',queue_rows,list(queue_rows[0]))
    qrows=[{'question_id':qid,**{s:exposure_by_question[qid].get(s,0) for s in ('E1','E2','E3','E4')}} for qid in sorted(exposure_by_question)]
    write_csv(args.out/'question_future_exposure.csv',qrows,['question_id','E1','E2','E3','E4'])
    report={'source_zip_sha256':digest,'scope':'100 frozen questions; top-5 final retrieved children from four full_002 runs','method':'UTC calendar-date comparison of preserved raw question_ts and child publication_time.raw_value; future iff publication date > question date','caveats':['Raw publication timestamps are not authenticated.','FUTURE is not equivalent to maliciousness or verified invalidity.','PAST_OR_SAME_DAY does not establish evidence validity.','Unreviewed answer aliases are not independently validated.','Recall@5 and nDCG@5 are NOT calculated; require independently reviewed relevance and an explicitly defined relevant-item universe.','Queue is a deduplicated union of top-5 retrieved occurrences, not the full candidate universe.'],'system_summary':stats,'bounded_annotation_pilot_items':len(pilot),'bounded_pilot_future_items':len(future_rows),'pooled_top5_unique_question_child_pairs':len(queue_rows),'top5_slots_total':len(retrieval),'future_exposure_question_union':sum(any(v for v in x.values()) for x in exposure_by_question.values())}
    (args.out/'posthoc_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('POSTHOC COMPLETE');print('Output:',args.out);print('Unique annotation pairs:',len(queue_rows));print('Question union with future top-5:',report['future_exposure_question_union']);print('System summary:')
    for row in stats: print(row)

if __name__=='__main__': main()
