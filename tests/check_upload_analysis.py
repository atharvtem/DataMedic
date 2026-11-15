import asyncio
import copy
import json
from unittest.mock import patch,AsyncMock
from datamedic.datasets import load_files,profile,Plan,execute
from streamlit.testing.v1 import AppTest
files=[('sales.csv',b'id,customer,amount,date\n1,A,10,2024-01-01\n2,B,20,2024-02-01\n2,B,20,2024-02-01\n3,C,bad,wrong\n4,,1000,2024-03-01\n'),('customers.json',b'[{"key":"A"},{"key":"B"}]')]
tables=load_files(files);before={k:v.copy(deep=True) for k,v in tables.items()}
plan=Plan.model_validate({'explanation':'Inspect files','checks':[
 {'table':'sales.csv','kind':'missing','reason':'Review blanks'},
 {'table':'sales.csv','kind':'duplicates','columns':['id'],'reason':'Review repeated IDs'},
 {'table':'sales.csv','kind':'invalid_number','columns':['amount'],'reason':'Review values'},
 {'table':'sales.csv','kind':'invalid_date','columns':['date'],'reason':'Review dates'},
 {'table':'sales.csv','kind':'missing_reference','columns':['customer'],'reference_table':'customers.json','reference_column':'key','reason':'Compare keys'}],
 'charts':[{'table':'sales.csv','kind':'time','x':'date','y':'amount','aggregation':'sum','period':'MS','reason':'Monthly amounts'}]})
findings,charts=execute(tables,plan)
assert [f['rows_to_review'] for f in findings]==[1,2,1,1,1]
assert list(charts[0]['data']['value'])==[10,40,1000]
for k in tables: assert tables[k].equals(before[k])
bad=plan.model_copy(deep=True);bad.checks[0].table='invented'
failed, surviving=execute(tables,bad)
assert failed[0]['status']=='failed' and failed[0]['rows_to_review'] is None
assert len(surviving)==1 and 'error' not in surviving[0]
assert failed[1]['status']=='completed'
print('Five checks, dynamic monthly chart, unknown-table rejection, and unchanged input passed')
from pathlib import Path
app=AppTest.from_file(str(Path('datamedic/ui.py').resolve()),default_timeout=60).run()
assert not app.exception
print('Upload landing page rendered')

from types import SimpleNamespace
files_ui=[SimpleNamespace(name=name,getvalue=lambda data=data:data) for name,data in files]
with patch('streamlit.file_uploader',return_value=files_ui),patch('datamedic.upload_ui.LLMPlanner') as planner:
    planner.return_value.generate=AsyncMock(return_value=plan)
    app=AppTest.from_file(str(Path('datamedic/ui.py').resolve()),default_timeout=60).run()
    app.text_area[0].set_value('Check missing keys and chart monthly amounts')
    app.button[0].click().run()
    assert not app.exception
    assert 'file_result' in app.session_state  # First submission already runs charts.
    app.button[1].click().run()
    assert not app.exception
    assert 'file_result' in app.session_state
    print('Upload, request, plan, run, findings UI passed')

# A grouped histogram uses a single set of numeric bins for directly comparable series.
people=load_files([('people.csv',b'sex,age,score\nMale,20,4\nMale,30,8\nFemale,21,6\nFemale,31,10\n')])
grouped=Plan.model_validate({'explanation':'Compare scores by sex','checks':[], 'charts':[{'table':'people.csv','kind':'histogram','x':'score','color_by':'sex','reason':'Separate men and women'}]})
_,charts=execute(people,grouped)
assert set(charts[0]['data']['group'])=={'Male','Female'}
assert charts[0]['data'].groupby('range').size().nunique()==1
filtered=grouped.model_copy(deep=True);filtered.charts[0].filter_column='sex';filtered.charts[0].filter_operator='equals';filtered.charts[0].filter_value='Female'
_,result=execute(people,filtered)
assert result[0]['data']['rows'].sum()==2 and set(result[0]['data']['group'])=={'Female'}
print('Grouped histogram, common bins and pre-chart filtering passed')

# Scalar checks expand by column, without relying on any dataset-specific names.
multi=plan.model_copy(deep=True)
multi.checks=[multi.checks[2].model_copy(update={'columns':['id','amount']})]
findings,charts=execute(tables,multi)
assert [f['columns'] for f in findings]==[['id'],['amount']]
assert [f['rows_to_review'] for f in findings]==[0,1]
multi.checks[0].columns=[]
multi.charts.insert(0,multi.charts[0].model_copy(update={'x':'absent'}))
findings,charts=execute(tables,multi)
assert findings[0]['status']=='failed'
assert charts[0]['error'] and 'error' not in charts[1]
for key in tables: assert tables[key].equals(before[key])
with patch('streamlit.file_uploader',return_value=files_ui),patch('datamedic.upload_ui.LLMPlanner') as planner:
    planner.return_value.generate=AsyncMock(return_value=multi)
    app=AppTest.from_file(str(Path('datamedic/ui.py').resolve()),default_timeout=60).run()
    app.text_area[0].set_value('Create charts even if a check fails')
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state['file_result'][1][0]['error']
    assert 'error' not in app.session_state['file_result'][1][1]
print('Multi-column expansion, isolated failures, automatic chart execution and read-only UI passed')

# Later provider failure must remain visible without losing an already drawn chart.
with patch('streamlit.file_uploader',return_value=files_ui),patch('datamedic.upload_ui.LLMPlanner') as planner:
    planner.return_value.generate=AsyncMock(side_effect=[plan,RuntimeError('provider unavailable')])
    app=AppTest.from_file(str(Path('datamedic/ui.py').resolve()),default_timeout=60).run()
    app.text_area[0].set_value('Investigate missing keys and chart monthly amounts')
    app.button[0].click().run()
    assert not app.exception
    assert len(app.session_state['file_result'][1])==1
    assert 'failed' in app.session_state['file_investigation']['stop_reason']
    assert app.session_state['file_investigation']['planning_calls']==2
    app.button[1].click().run()
    assert not app.exception
    assert 'file_investigation' not in app.session_state

with patch('streamlit.file_uploader',return_value=files_ui),patch('datamedic.upload_ui.LLMPlanner') as planner:
    planner.return_value.generate=AsyncMock(return_value=plan)
    app=AppTest.from_file(str(Path('datamedic/ui.py').resolve()),default_timeout=60).run()
    app.checkbox[0].uncheck()
    app.text_area[0].set_value('Make a chart without follow-ups')
    app.button[0].click().run()
    assert not app.exception
    assert planner.return_value.generate.await_count==1
    assert 'file_investigation' not in app.session_state
print('Follow-up failure preservation, history invalidation and single-plan option UI passed')

# Unsupported requests must not imply a clean dataset when nothing was measured.
empty=Plan(explanation='Need a definition',checks=[],charts=[],unsupported=['Specify the conversion denominator.'])
with patch('streamlit.file_uploader',return_value=files_ui),patch('datamedic.upload_ui.LLMPlanner') as planner:
    planner.return_value.generate=AsyncMock(return_value=empty)
    app=AppTest.from_file(str(Path('datamedic/ui.py').resolve()),default_timeout=60).run()
    app.text_area[0].set_value('Calculate an undefined conversion rate')
    app.button[0].click().run()
    assert not app.exception
    assert any('No data-quality conclusion' in item.value for item in app.markdown)
    assert any('denominator' in item.value for item in app.warning)
print('Unmeasured requests show clarification without a clean-data claim')
