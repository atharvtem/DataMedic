"""Reproducible evidence-replay regression suite seeded by a live MCP capture."""
import argparse
import asyncio
import copy
import hashlib
import json
import statistics
import time
from pathlib import Path
from datamedic.agent.graph import investigate
from datamedic.agent.models import Alert
from datamedic.agent.transport import MCPTransport

class Replay:
    def __init__(self, results):
        self.results = results
    async def call(self, server, name, arguments):
        return copy.deepcopy(self.results[name])


def cases(results):
    yield 'missing-ingestion', results, 12, 'MISSING_INGESTION'
    for name,tool,change in [
        ('missing-etl','query_etl_pipeline_logs',lambda r:r.update(records=[])),
        ('service-conflict','check_upstream_service_events',lambda r:r['records'][0]['details'].update(status='OUTAGE')),
        ('configuration-conflict','inspect_config_deployments',lambda r:r['records'][0]['details'].update(status='CHANGED')),
        ('mismatched-etl-window','query_etl_pipeline_logs',lambda r:[e['details'].update(window_start='2018-08-14T00:00:00') for e in r['records']]),
        ('failed-coverage','check_payment_coverage',lambda r:r.update(ok=False,code='TIMEOUT')),
    ]:
        fixture=copy.deepcopy(results)
        change(fixture[tool])
        yield name,fixture,12,'ESCALATE_AMBIGUOUS'
    yield 'insufficient-budget',results,3,'ESCALATE_AMBIGUOUS'

async def run(output: Path, repeats: int):
    # Collect actual responses; replay mutations never alter the database.
    live=await investigate(Alert(text='Payment coverage anomaly'),MCPTransport())
    results={h['tool']:h['result'] for h in live['history']}
    if live['report']['verdict']!='MISSING_INGESTION':
        raise RuntimeError('Load the documented missing-ingestion incident before capturing fixtures')
    snapshot=json.dumps(results,sort_keys=True).encode()
    runs=[]
    for name,fixture,budget,expected in cases(results):
        for repeat in range(repeats):
            started=time.monotonic()
            trace=await investigate(Alert(text='Payment coverage anomaly',budget=budget),Replay(fixture))
            report=trace['report']
            runs.append(dict(case=name,repeat=repeat,expected=expected,predicted=report['verdict'],
                correct=report['verdict']==expected,points=report['points_spent'],
                elapsed_ms=round((time.monotonic()-started)*1000,3),trace=trace))
    tp=sum(r['expected']==r['predicted']=='ESCALATE_AMBIGUOUS' for r in runs)
    fp=sum(r['predicted']=='ESCALATE_AMBIGUOUS' and r['expected']!='ESCALATE_AMBIGUOUS' for r in runs)
    fn=sum(r['expected']=='ESCALATE_AMBIGUOUS' and r['predicted']!='ESCALATE_AMBIGUOUS' for r in runs)
    result=dict(suite='olist-evidence-replay-v1',split='development',planner='deterministic-olist-v1',
        source_sha256=hashlib.sha256(snapshot).hexdigest(),source_capture=live,
        limitations='Evidence replay regression checks, not held-out diagnosis accuracy or real query latency benchmarks. No LLM baselines have been run.',
        summary=dict(runs=len(runs),correct=sum(r['correct'] for r in runs),
            abstention_precision=tp/(tp+fp) if tp+fp else None,
            abstention_recall=tp/(tp+fn) if tp+fn else None,
            median_replay_ms=statistics.median(r['elapsed_ms'] for r in runs)),runs=runs)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['summary'],indent=2))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('/tmp/datamedic-regression.json'))
    parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args()
    if not 1<=args.repeats<=10:
        parser.error('--repeats must be 1–10')
    asyncio.run(run(args.output,args.repeats))

if __name__=='__main__':
    main()
