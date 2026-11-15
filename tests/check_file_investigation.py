"""Offline acceptance scenarios; no credentials or live provider calls."""
import asyncio
import json
from unittest.mock import AsyncMock
from types import SimpleNamespace
from datamedic.datasets import Plan, load_files
from datamedic.file_investigation import investigate_files


def plan(checks=(), charts=()):
    return Plan(explanation='Inspect relevant evidence', checks=list(checks), charts=list(charts))


def check(kind='summary', column='reading'):
    return {'table':'sensor.csv','kind':kind,'columns':[column],'reason':'Inspect readings'}


chart={'table':'sensor.csv','kind':'histogram','x':'reading','reason':'Requested distribution'}


async def run():
    for malformed in (False, True):
        tables=load_files([('sensor.csv',('reading,label\n1,PRIVATE_CELL\n2,B\n'+('broken' if malformed else '3')+',C\n').encode())])
        before=tables['sensor.csv'].copy(deep=True)
        prompts=[]
        async def choose(prompt, schema, system):
            prompts.append(prompt)
            if not prompt['evidence']['checks']:
                return plan([check()], [chart])
            summary=prompt['evidence']['checks'][0]['details']
            if summary['unreadable_numbers'] and len(prompt['evidence']['checks'])==1:
                return plan([check('invalid_number')])
            return plan()
        result=await investigate_files(tables,['Inspect readings and draw a histogram'],SimpleNamespace(generate=choose))
        assert result.steps==(3 if malformed else 2)
        assert len(result.charts)==1 and not result.charts[0].get('error')
        if malformed: assert result.findings[1]['rows_to_review']==1
        assert tables['sensor.csv'].equals(before)
        assert 'PRIVATE_CELL' not in json.dumps(prompts)
        assert 'example_row_numbers' not in json.dumps(prompts)
        assert 'values' not in prompts[-1]['evidence']['charts'][0]

    tables=load_files([('sensor.csv',b'reading,label\n1,A\n2,B\n3,C\n')])
    # Invalid column can be repaired; the previously successful chart is retained.
    mock=AsyncMock(side_effect=[plan([check(column='absent')],[chart]),plan([check()]),plan()])
    result=await investigate_files(tables,['Inspect readings'],SimpleNamespace(generate=mock))
    assert [f['status'] for f in result.findings]==['failed','completed']
    assert len(result.charts)==1 and result.steps==3

    # A rewritten reason does not bypass duplicate suppression.
    repeated=check();repeated['reason']='A different justification'
    mock=AsyncMock(side_effect=[plan([check()]),plan([repeated])])
    result=await investigate_files(tables,['Inspect'],SimpleNamespace(generate=mock))
    assert result.steps==1 and result.calls==2 and 'repeated' in result.stop_reason

    # Expanded columns cost separate steps, including failed executions.
    multi=check();multi['columns']=['reading','label','absent']
    result=await investigate_files(tables,['Inspect'],SimpleNamespace(generate=AsyncMock(return_value=plan([multi],[chart]))),max_steps=2)
    assert result.steps==2 and len(result.findings)==2 and not result.charts
    assert 'budget' in result.stop_reason

    # Follow-up provider failure keeps successful evidence and charts.
    mock=AsyncMock(side_effect=[plan([check()],[chart]),RuntimeError('private provider response')])
    result=await investigate_files(tables,['Inspect'],SimpleNamespace(generate=mock))
    assert result.steps==2 and len(result.charts)==1 and 'failed' in result.stop_reason
    assert 'private' not in result.stop_reason
    async def slow(*args,**kwargs):
        await asyncio.sleep(1)
    result=await investigate_files(tables,['Inspect'],SimpleNamespace(generate=slow),timeout=.001)
    assert result.steps==0 and 'timed out' in result.stop_reason
    mock=AsyncMock(return_value=plan([check()]))
    result=await investigate_files(tables,['Inspect'],SimpleNamespace(generate=mock),max_rounds=1)
    assert result.calls==1 and 'round limit' in result.stop_reason
    # A malformed provider plan gets a bounded repair attempt with safe diagnostics.
    from pydantic import ValidationError
    try:
        Plan.model_validate({'explanation':'PRIVATE_PROVIDER_PAYLOAD','checks':'SECRET_VALUE','charts':[]})
    except ValidationError as exc:
        invalid_plan=exc
    mock=AsyncMock(side_effect=[plan(charts=[chart]),invalid_plan,plan([check()]),plan()])
    result=await investigate_files(tables,['Inspect'],SimpleNamespace(generate=mock))
    assert result.calls==4 and result.steps==2 and len(result.charts)==1
    assert result.planning_errors[0]['code']=='INVALID_PLAN'
    repair_prompt=mock.await_args_list[2].args[0]
    assert repair_prompt['planning_feedback']['errors'][0]['path']==['checks']
    assert 'SECRET_VALUE' not in json.dumps(repair_prompt)
    assert 'PRIVATE_PROVIDER_PAYLOAD' not in json.dumps(repair_prompt)
    assert mock.await_args_list[3].args[0]['planning_feedback'] is None
    result=await investigate_files(tables,['Inspect'],SimpleNamespace(generate=AsyncMock(side_effect=invalid_plan)))
    assert result.calls==4 and result.steps==0 and len(result.planning_errors)==4
    assert 'round limit' in result.stop_reason
    limited=SimpleNamespace(generate=AsyncMock(side_effect=[plan(charts=[chart]),RuntimeError('provider secret')]),
                            errors=[{'code':'HTTP_429'}])
    result=await investigate_files(tables,['Inspect'],limited)
    assert result.calls==2 and len(result.charts)==1
    assert 'rate-limited' in result.stop_reason and 'quota' in result.stop_reason
    assert result.planning_errors==[{'round':2,'code':'HTTP_429'}]
    print('Evidence-dependent follow-ups, repair, deduplication, budgets, read-only inputs, privacy, provider failure and timeout passed')


asyncio.run(run())
