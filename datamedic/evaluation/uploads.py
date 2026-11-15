"""Live upload-workspace development checks using synthetic data only."""
import argparse
import asyncio
import json
import time
import sys
from pathlib import Path

from datamedic.agent.llm import LLMPlanner
from datamedic.datasets import load_files
from datamedic.file_investigation import investigate_files


def fixtures():
    yield ('malformed-readings', [('sensor.csv', b'reading,station\n10,A\n11,A\n12,B\nbroken,B\n,A\n13,B\n')],
           'Show a histogram of reading and investigate missing or unreadable readings. Do not infer business rules.')
    yield ('chart-only', [('visits.csv', b'zone\nNorth\nSouth\nNorth\nEast\nSouth\nNorth\n')],
           'Only show a category chart counting rows by zone in visits.csv. Do not run data checks.')

    for dirty in (False, True):
        tail = 'unreadable' if dirty else '8'
        yield ('conditional-dirty' if dirty else 'conditional-clean',
               [('batches.csv', f'mass,lot\n2,L1\n4,L2\n6,L3\n{tail},L4\n'.encode())],
               'First run a numeric summary of mass in batches.csv. Only AFTER inspecting that result, '
               'if it reports unreadable numbers, run invalid_number on mass to locate those rows. '
               'Otherwise stop. Do not create charts or run unrelated checks.')
    yield ('reference-coverage', [
        ('shipments.csv', b'part,units\nP1,3\nP2,7\nP9,2\n,1\nP9,4\n'),
        ('catalog.csv', b'code\nP1\nP2\nP3\n')],
        'Check shipments.csv part values missing from catalog.csv code. '
        'Check blank shipment part values separately. Do not assume either key is unique or modify data.')
    yield ('ambiguous-rate', [('funnel.csv', b'visitors,orders\n100,12\n80,9\n')],
        'Calculate our conversion rate. We have not specified which events qualify or the denominator. '
        'Explain what definition is missing; do not guess or substitute row percentages.')


def assess(case, tables, before, result):
    checks = {
        'read_only': all(tables[name].equals(frame) for name, frame in before.items()),
        'bounded': result.steps <= 11 and result.calls <= 4,
        'no_failed_operations': all(f['status'] == 'completed' for f in result.findings) and all(not c.get('error') for c in result.charts),
        'normal_stop': result.stop_reason.startswith('The planner selected no further supported steps.'),
    }
    if case == 'malformed-readings':
        for kind in ('missing', 'invalid_number'):
            checks[kind] = any(f['table']=='sensor.csv' and f['check']==kind and 'reading' in f['columns']
                               and f['rows_checked']==6 and f['rows_to_review']==1 for f in result.findings)
        checks['histogram'] = any(not c.get('error') and c['spec']['table']=='sensor.csv'
                                  and c['spec']['kind']=='histogram' and c['spec']['x']=='reading'
                                  and c['data']['rows'].sum()==4 for c in result.charts)
        checks['requested_scope'] = len(result.findings)==2 and {f['check'] for f in result.findings}=={'missing','invalid_number'} and len(result.charts)==1
    elif case == 'chart-only':
        checks['no_unrequested_checks'] = not result.findings
        checks['category_counts'] = any(not c.get('error') and c['spec']['table']=='visits.csv'
            and c['spec']['kind']=='category' and c['spec']['x']=='zone'
            and c['spec']['aggregation']=='count' and not c['spec']['color_by']
            and dict(zip(c['data']['group'], c['data']['value']))=={'North':3,'South':2,'East':1}
            for c in result.charts)
    elif case.startswith('conditional-'):
        dirty = case == 'conditional-dirty'
        summaries = [f for f in result.findings if f['check']=='summary' and f['columns']==['mass']]
        checks['summary_measurements'] = bool(summaries) and summaries[0]['details'].get('unreadable_numbers')==int(dirty) and summaries[0]['details'].get('mean')==(4 if dirty else 5)
        invalid = [f for f in result.findings if f['check']=='invalid_number' and f['columns']==['mass']]
        checks['conditional_choice'] = len(invalid)==int(dirty) and (not dirty or invalid[0]['rows_to_review']==1)
        checks['requested_scope'] = not result.charts and len(result.findings)==(2 if dirty else 1)
        if dirty:
            rounds = {h['operation']['kind']:h['round'] for h in result.history if h['kind']=='check'}
            checks['follow_up_after_evidence'] = rounds.get('invalid_number',0)>rounds.get('summary',5)
    elif case == 'reference-coverage':
        checks['missing_reference_count'] = any(f['table']=='shipments.csv' and f['check']=='missing_reference'
            and f['columns']==['part'] and f['rows_to_review']==2 for f in result.findings)
        checks['separate_blank_count'] = any(f['table']=='shipments.csv' and f['check']=='missing'
            and 'part' in f['columns'] and f['rows_to_review']==1 for f in result.findings)
        checks['reference_target'] = any(h['operation'].get('reference_table')=='catalog.csv'
            and h['operation'].get('reference_column')=='code' for h in result.history)
    elif case == 'ambiguous-rate':
        checks['missing_definition_reported'] = any('denominator' in message.lower() for message in result.plan.unsupported)
        checks['no_substitute_calculation'] = not result.charts and not result.findings
    else:
        raise ValueError(f'Unknown evaluation case: {case}')
    return checks


async def run(providers, selected_cases=None, repeats=1):
    if not 1 <= repeats <= 3:
        raise ValueError('Use 1–3 repeats.')
    runs=[]
    for provider in providers:
        for repeat, (name, files, request) in ((repeat, fixture) for repeat in range(1,repeats+1) for fixture in fixtures()):
            if selected_cases and name not in selected_cases:
                continue
            tables=load_files(files)
            before={name:frame.copy(deep=True) for name,frame in tables.items()}
            started=time.monotonic()
            try:
                planner=LLMPlanner(provider)
            except ValueError:
                runs.append({'provider':provider,'case':name,'repeat':repeat,'passed':False,'error':'Provider not configured'})
                continue
            result=await investigate_files(tables,[request],planner,
                on_progress=lambda message: print(f'{provider}/{name}: {message}', file=sys.stderr, flush=True))
            checks=assess(name,tables,before,result)
            record={'provider':provider,'case':name,'repeat':repeat,'passed':all(checks.values()),'checks':checks,
                    'elapsed_seconds':round(time.monotonic()-started,2),'steps':result.steps,
                    'planning_calls':result.calls,'tokens':planner.tokens,'models':planner.calls,
                    'provider_errors':planner.errors,'planning_errors':result.planning_errors,'stop_reason':result.stop_reason,
                    'unsupported':result.plan.unsupported,'explanation':result.plan.explanation,'history':result.history}
            runs.append(record)
            print(json.dumps(record),flush=True)
    return {'suite':'upload-live-development-v3','limitations':'Synthetic development smoke tests, not a held-out benchmark or proof of general investigation quality. Token usage is reported; monetary cost is not estimated.',
            'repeats':repeats,'passed':sum(r['passed'] for r in runs),'total':len(runs),'runs':runs}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider',choices=['groq','gemini','both'],default='both')
    parser.add_argument('--output',type=Path,default=Path('/tmp/datamedic-upload-evaluation.json'))
    parser.add_argument('--case',action='append',choices=[case[0] for case in fixtures()],help='Run only selected cases; repeat to select more than one.')
    parser.add_argument('--repeats',type=int,choices=range(1,4),default=1)
    args=parser.parse_args()
    result=asyncio.run(run(['groq','gemini'] if args.provider=='both' else [args.provider], args.case, args.repeats))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(f"Passed {result['passed']}/{result['total']}; report: {args.output}")
    raise SystemExit(0 if result['passed']==result['total'] else 1)


if __name__=='__main__':
    main()
