"""Ensure the expanded evaluator accepts correct evidence and rejects omissions."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from datamedic.datasets import Plan, load_files
from datamedic.file_investigation import investigate_files
from datamedic.evaluation.uploads import fixtures, assess, run


def plan(checks=(), charts=(), unsupported=()):
    return Plan(explanation='Fixture', checks=list(checks), charts=list(charts), unsupported=list(unsupported))


def check(table, kind, columns, **kwargs):
    return dict(table=table, kind=kind, columns=columns, reason='Fixture', **kwargs)


async def main():
    for name, files, request in fixtures():
        tables=load_files(files)
        before={k:v.copy(deep=True) for k,v in tables.items()}
        if name=='malformed-readings':
            sequence=[plan([check('sensor.csv',k,['reading']) for k in ['missing','invalid_number']],
                [dict(table='sensor.csv',kind='histogram',x='reading',reason='Fixture')])]
        elif name=='chart-only':
            sequence=[plan(charts=[dict(table='visits.csv',kind='category',x='zone',reason='Fixture')])]
        elif name.startswith('conditional-'):
            sequence=[plan([check('batches.csv','summary',['mass'])])]
            if name.endswith('dirty'): sequence.append(plan([check('batches.csv','invalid_number',['mass'])]))
        elif name=='reference-coverage':
            sequence=[plan([check('shipments.csv','missing_reference',['part'],reference_table='catalog.csv',reference_column='code'),
                            check('shipments.csv','missing',['part'])])]
        else:
            sequence=[plan(unsupported=['Define qualifying events and denominator.'])]
        sequence.append(plan())
        result=await investigate_files(tables,[request],SimpleNamespace(generate=AsyncMock(side_effect=sequence)))
        verdict=assess(name,tables,before,result)
        assert all(verdict.values()), (name,verdict)
        # An empty run must not accidentally count as successful fulfillment.
        empty=await investigate_files(tables,[request],SimpleNamespace(generate=AsyncMock(return_value=plan())))
        assert not all(assess(name,tables,before,empty).values()), name
        if name=='malformed-readings':
            result.findings.append({**result.findings[0], 'check':'summary'})
            assert not assess(name,tables,before,result)['requested_scope']
        if name=='conditional-dirty':
            for h in result.history: h['round']=1
            assert not assess(name,tables,before,result)['follow_up_after_evidence']
    def fake_planner(provider):
        return SimpleNamespace(generate=AsyncMock(side_effect=[plan(charts=[dict(table='visits.csv',kind='category',x='zone',reason='Fixture')]),plan()]),
                               tokens=0,calls=[],errors=[])
    with patch('datamedic.evaluation.uploads.LLMPlanner',side_effect=fake_planner), patch('builtins.print'):
        report=await run(['groq','gemini'],['chart-only'],repeats=2)
    assert report['passed']==report['total']==4
    assert {(r['provider'],r['repeat']) for r in report['runs']}=={('groq',1),('groq',2),('gemini',1),('gemini',2)}
    try:
        await run(['groq'],repeats=4)
    except ValueError:
        pass
    else:
        raise AssertionError('Unbounded repeat count accepted')
    print('Six evaluation oracles accept correct results and reject omissions/premature follow-ups')


asyncio.run(main())
