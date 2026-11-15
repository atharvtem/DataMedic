"""Verify chart composition across unrelated column names, aggregations and groups."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import pandas as pd
from streamlit.testing.v1 import AppTest
from datamedic.datasets import Plan,execute,load_files
from datamedic.charts import render_chart

for names in [('zone','batch','quantity','cost','day'),('segment','variant','reading','weight','recorded')]:
    category,series,x,y,date=names
    content=(','.join(names)+'\nA,R,1,10,2024-01-01\nA,S,2,20,2024-01-02\nA,R,3,30,2024-01-03\nB,S,4,40,2024-02-01\nB,,5,50,2024-02-02\n').encode()
    tables=load_files([('arbitrary.csv',content)]); original=tables['arbitrary.csv'].copy(deep=True)
    for kind in ['histogram','category','time','scatter','box']:
        for grouped in [False,True]:
            for aggregation in ['count','sum','mean','median'] if kind in {'category','time'} else ['count']:
                spec={'table':'arbitrary.csv','kind':kind,'x':date if kind=='time' else category if kind in {'category','box'} else x,
                      'y':y if kind!='histogram' else None,'color_by':series if grouped else None,'aggregation':aggregation,'period':'MS','reason':'Compare observed groups'}
                plan=Plan.model_validate({'explanation':'Compare','checks':[],'charts':[spec]})
                _,charts=execute(tables,plan);result=charts[0]
                assert 'error' not in result,result
                render_chart(result).to_dict(validate=True)
                frame=result['data']
                if grouped: assert set(frame['group' if kind=='histogram' else 'series'])=={'R','S','(missing)'}
                if kind=='histogram': assert frame['rows'].sum()==5
                if kind in {'category','time'}:
                    if aggregation=='count': assert frame['value'].sum()==5
                    if aggregation=='sum': assert frame['value'].sum()==150
                    if grouped and aggregation in {'mean','median'}:
                        assert frame.loc[frame['series']=='R','value'].iloc[0]==20
                if kind=='scatter': assert len(frame)==5
                if kind=='box': assert frame['rows'].sum()==5
                # Filters operate before every chart computation.
                plan.charts[0].filter_column=x;plan.charts[0].filter_operator='greater_than';plan.charts[0].filter_value='2'
                _,filtered=execute(tables,plan)
                assert 'error' not in filtered[0]
                render_chart(filtered[0]).to_dict(validate=True)
                assert tables['arbitrary.csv'].equals(original)
    charts=[{'table':'arbitrary.csv','kind':kind,'x':date if kind=='time' else category,'y':y,'aggregation':'sum','period':'MS','color_by':series,'reason':'Compare groups'} for kind in ['category','time','box']]
    plan=Plan.model_validate({'explanation':'Grouped charts','checks':[],'charts':charts})
    with patch('streamlit.file_uploader',return_value=[SimpleNamespace(name='arbitrary.csv',getvalue=lambda:content)]),patch('datamedic.upload_ui.LLMPlanner') as planner:
        planner.return_value.generate=AsyncMock(return_value=plan)
        app=AppTest.from_file(str(Path('datamedic/ui.py').resolve()),default_timeout=60).run()
        app.text_area[0].set_value('Compare groups in charts');app.button[0].click().run()
        assert not app.exception
        assert not app.warning
        assert all('error' not in c for c in app.session_state['file_result'][1])
print('All five chart types: grouped/ungrouped, aggregates, filters, renamed fields, rendered schemas, UI and unchanged data passed')

# Numeric category ordering is independent of source-row order and field names.
from datamedic.charts import category_order
assert category_order(['10','2','1','-3','1.5','0'])==['-3','0','1','1.5','2','10']
assert category_order(['001','1','01'])==['001','01','1']  # Preserve distinct ID labels.
assert category_order(['Z','a','B'])==['a','B','Z']
assert category_order(['NaN','2'])==['2','NaN']
fixture=load_files([('counts.csv',b'level,cohort,amount\n10,10,3\n2,2,4\n1,1,5\n0,2,6\n21,1,7\n')])
for kind in ['category','box']:
    plan=Plan.model_validate({'explanation':'Ordered groups','checks':[], 'charts':[{'table':'counts.csv','kind':kind,'x':'level','y':'amount','color_by':'cohort','reason':'Compare'}]})
    for table in [fixture,{'counts.csv':fixture['counts.csv'].sample(frac=1,random_state=4)}]:
        _,results=execute(table,plan)
        spec=render_chart(results[0]).to_dict(validate=True)
        enc=spec['encoding'] if kind=='category' else spec['layer'][0]['encoding']
        assert enc['x']['sort']==['0','1','2','10','21']
        assert enc['x']['axis']['labelAngle']==0
        assert enc['color']['sort']==['1','2','10']
        assert enc['xOffset']['sort']==['1','2','10']
print('Numeric/decimal/negative ordering, distinct labels, legends and shuffled-row stability passed')

# Percent denominators are computed after filters but before top-category truncation.
import math
percent_tables=load_files([('shares.csv',b'item,team,number\nA,X,1\nA,X,2\nA,Y,3\nB,Y,4\nB,Y,5\nB,Y,6\n')])
for kind in ['category','histogram','time']:
    source=percent_tables if kind!='time' else load_files([('shares.csv',b'item,team,number\n2024-01-01,X,1\n2024-01-02,X,2\n2024-01-03,Y,3\n2024-02-01,Y,4\n2024-02-02,Y,5\n2024-02-03,Y,6\n')])
    for normalization in ['all_rows','within_series']+(['within_category'] if kind!='histogram' else []):
        p=Plan.model_validate({'explanation':'Shares','checks':[],'charts':[{'table':'shares.csv','kind':kind,'x':'number' if kind=='histogram' else 'item','color_by':'team','period':'MS','normalization':normalization,'reason':'Compare row shares'}]})
        _,result=execute(source,p);r=result[0];assert 'error' not in r,r
        f=r['data'];render_chart(r).to_dict(validate=True)
        if normalization=='all_rows': assert math.isclose(f['share'].sum(),1) and set(f['denominator'])=={6}
        elif normalization=='within_series': assert all(math.isclose(v,1) for v in f.groupby('group' if kind=='histogram' else 'series')['share'].sum())
        else: assert all(math.isclose(v,1) for v in f.groupby('group')['share'].sum())
        p.charts[0].filter_column='team';p.charts[0].filter_operator='equals';p.charts[0].filter_value='Y'
        _,filtered=execute(source,p)
        original_spec=render_chart(r).to_dict();filtered_spec=render_chart(filtered[0]).to_dict()
        assert original_spec['encoding']['color']['scale']==filtered_spec['encoding']['color']['scale']
        assert '2 rows removed by chart filters' in filtered[0]['note']
        if normalization=='all_rows': assert set(filtered[0]['data']['denominator'])=={4}

many=load_files([('long.csv',('label\n'+'\n'.join(f'Long category description {i}' for i in range(35))).encode())])
p=Plan.model_validate({'explanation':'Labels','checks':[],'charts':[{'table':'long.csv','kind':'category','x':'label','normalization':'all_rows','reason':'Review'}]})
_,result=execute(many,p);r=result[0];spec=render_chart(r).to_dict(validate=True)
assert set(r['data']['denominator'])=={35} and math.isclose(r['data']['share'].sum(),30/35)
assert spec['encoding']['y']['field']=='group' and spec['height']>=30*26
assert spec['encoding']['x']['scale']['domain']==[0,1]
p.charts[0].aggregation='mean'
_,bad=execute(many,p);assert 'error' in bad[0]
print('Percent denominators, filtered colours, horizontal labels, honest top-category shares and count-only validation passed')

# Missing measurements should break time lines; UTC avoids local-time day shifts.
t=load_files([('gaps.csv',b'day,team,reading\n2024-01-01,A,2\n2024-03-01,A,4\n2024-02-01,B,8\n')])
p=Plan.model_validate({'explanation':'Gaps','checks':[],'charts':[{'table':'gaps.csv','kind':'time','x':'day','y':'reading','aggregation':'mean','period':'MS','color_by':'team','reason':'Measurements'}]})
_,r=execute(t,p);f=r[0]['data']
assert len(f)==6 and f['value'].isna().sum()==3
spec=render_chart(r[0]).to_dict(validate=True)
assert spec['mark']['invalid']=='break-paths-show-domains'
assert spec['encoding']['x']['scale']['type']=='utc'
print('Missing time measurements remain gaps and temporal axes use UTC passed')

with patch('streamlit.file_uploader',return_value=[SimpleNamespace(name='shares.csv',getvalue=lambda:b'item,team\nA,X\nA,Y\nB,Y\n')]),patch('datamedic.upload_ui.LLMPlanner') as planner:
    planner.return_value.generate=AsyncMock(return_value=Plan.model_validate({'explanation':'Counts','checks':[],'charts':[{'table':'shares.csv','kind':'category','x':'item','color_by':'team','reason':'Compare'}]}))
    app=AppTest.from_file(str(Path('datamedic/ui.py').resolve()),default_timeout=60).run()
    app.text_area[0].set_value('Show counts by team');app.button[0].click().run()
    app.selectbox(key='measure-0').set_value('within_category').run()
    app.button[1].click().run()
    assert not app.exception
    plotted=app.session_state['file_result'][1][0]
    assert plotted['spec']['normalization']=='within_category'
    assert all(math.isclose(value,1) for value in plotted['data'].groupby('group')['share'].sum())
print('Counts-to-percentage UI control and recalculation passed')
