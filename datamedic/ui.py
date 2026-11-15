"""Reviewable local incident investigation UI."""
import asyncio
import json
import time
from datetime import date, timedelta
import pandas as pd
from datamedic.metrics import summarize
import streamlit as st
from datamedic.agent.graph import investigate
from datamedic.agent.models import Alert
from datamedic.agent.llm import LLMPlanner
from datamedic.agent.transport import MCPTransport

st.set_page_config(page_title='DataMedic',page_icon='🩺',layout='wide')
mode=st.sidebar.radio('Workspace',['Your files','Olist example'])
if mode=='Your files':
    from datamedic.upload_ui import render
    render()
    st.stop()
st.title('DataMedic')
st.caption('Investigate payment anomalies with evidence, competing hypotheses, and a fixed tool budget.')
st.info('Demo scope: payment coverage in Olist. The August 15, 2018 incident was deliberately seeded. Other dates show actual loaded metrics, but have no seeded operations evidence.')
st.subheader('1. Check the numbers')
with st.form('measure'):
    selected=st.date_input('Purchase date',date(2018,8,15))
    measure=st.form_submit_button('Load payment comparison',type='primary')
if measure:
    st.session_state.pop('trace',None)
    st.session_state.pop('comparison',None)
    try:
        with st.spinner('Reading eight days of payment metrics…'):
            result=asyncio.run(MCPTransport().call('database','check_payment_coverage',
                {'start':(selected-timedelta(days=7)).isoformat(),'end':(selected+timedelta(days=1)).isoformat()}))
        st.session_state['comparison']=summarize(selected,result)
        st.session_state['measured_day']=selected
    except Exception:
        st.error('Could not load this comparison. Check that the database and MCP services are running.')
if 'comparison' not in st.session_state:
    st.caption('Start with 2018-08-15, then try 2018-08-14 or 2018-08-16. Changing the date measures a different window; it does not create another incident.')
    st.stop()
summary=st.session_state['comparison']
day=st.session_state['measured_day']
target=summary['target']
st.write(f'Comparison for **{day.isoformat()}** against the seven preceding calendar days.')
a,b,c=st.columns(3)
a.metric('Recorded payment value',f"{target['payment_value']:,.2f}")
b.metric('Previous 7-day daily average',f"{summary['average']:,.2f}")
c.metric('Change from average',f"{summary['change']:+.2f}%" if summary['change'] is not None else 'No reference value')
chart=pd.DataFrame([{'Date':r['date'],'Recorded payments':float(r['payment_value']),
                    'Previous 7-day average':float(summary['average'])} for r in summary['days']]).set_index('Date')
st.line_chart(chart)
st.dataframe(pd.DataFrame([{**r,'payment_value':float(r['payment_value'])} for r in summary['days']]),hide_index=True,width='stretch')
st.caption('Payment values are summed after joining payment rows to orders by purchase date. Percentage change = (selected-day value ÷ previous seven-day average − 1) × 100. Empty calendar days count as zero in the average.')
if not summary['complete']:
    st.warning('One or more dates have no orders in the loaded data. The average includes those zero days; missing source coverage may make the comparison misleading.')
if not target['orders']:
    st.warning('No orders exist for the selected date. Choose a date with data before investigating.')
    st.stop()
if summary['change'] is not None:
    st.write(f"The measured value is **{abs(summary['change']):.2f}% {'below' if summary['change']<0 else 'above'}** the reference average. This comparison alone does not establish an incident or its cause.")
st.write(f"**{target['orders']} orders**, **{target['paid_orders']} with payments**, **{target['missing_orders']} without payments**; payment coverage is **{target['coverage']:.2f}%**.")
st.caption('This manual preview is outside the investigation budget. The agent independently rechecks evidence during the run.')
st.subheader('2. Investigate the cause')
if day!=date(2018,8,15):
    st.warning('Only August 15 has matching synthetic ETL, service, and configuration records. Other dates may escalate even when a payment-value change is visible.')
with st.form('incident'):
    context=st.text_area('Optional context (not a SQL query)','')
    a,b=st.columns(2)
    budget=a.number_input('Tool-point budget',min_value=0,max_value=100,value=12)
    provider=b.selectbox('Planner',['deterministic','groq','gemini'])
    submitted=st.form_submit_button('Investigate measured date',type='primary')
text=f"Recorded payment value on {day} is {target['payment_value']}; prior seven-day average is {summary['average']:.2f}; payment coverage is {target['coverage']:.2f}%. {context}"
if submitted:
    st.session_state.pop('trace',None)
    try:
        planner=None if provider=='deterministic' else LLMPlanner(provider)
        started=time.monotonic()
        with st.status('Investigating…',expanded=True) as progress:
            live_hypotheses=st.empty()
            live_budget=st.empty()
            seen=set()
            def update(state):
                live_budget.write(f"Points remaining: {state['remaining']}")
                if state['hypotheses']:
                    live_hypotheses.dataframe(state['hypotheses'],width='stretch')
                for call in state['history']:
                    if call['id'] not in seen:
                        st.write(f"{call['id']}: {call['tool']} — {call['cost']} points — {'OK' if call['result'].get('ok') else call['result'].get('code','failed')}")
                        seen.add(call['id'])
            trace=asyncio.run(investigate(Alert(text=text,purchase_date=day,budget=budget),MCPTransport(),planner,on_update=update))
            progress.update(label='Investigation finished',state='complete',expanded=False)
        st.session_state['trace']=trace
        st.session_state['elapsed']=time.monotonic()-started
    except ValueError as exc:
        st.error(str(exc))
    except Exception:
        st.error('Investigation could not finish. Check service health and provider configuration.')
if 'trace' in st.session_state:
    trace=st.session_state['trace']; report=trace['report']
    (st.success if report['verdict']=='MISSING_INGESTION' else st.warning)(report['verdict'].replace('_',' '))
    st.write(report['reason'])
    st.info('SUPPORTED means the evidence favors this cause. WEAKENED means an alternative is less supported, not impossible. Escalation means the app cannot establish a cause; it does not mean the data is healthy.')
    for error in report.get('provider_errors',[]):
        st.error(f"{error['provider']} request failed ({error['code']}). Check model availability, API access, and quota.")
    a,b,c=st.columns(3)
    a.metric('Points spent',report['points_spent']);b.metric('Points remaining',report['points_remaining']);c.metric('Elapsed',f"{st.session_state['elapsed']:.1f}s")
    st.subheader('Hypotheses')
    st.dataframe(trace['hypotheses'],width='stretch')
    st.subheader('Evidence trail')
    for entry in trace['history']:
        with st.expander(f"{entry['id']} · {entry['tool']} · {entry['cost']} points · {entry['elapsed_ms']} ms"):
            st.json(entry['arguments'])
            st.json(entry['result'])
            st.dataframe(entry.get('hypotheses_after',[]),width='stretch')
    st.caption('Points are investigation budget units, not money. A result at 8/12 means the checks used eight available points.')
    st.subheader('What should you do next?')
    st.write('The app diagnoses; it has not repaired any records. For a real incident, compare the original payment export with imported keys, restore missing records through the normal pipeline, then recheck coverage. For this seeded demo, this is a suggested next action—not work already performed.')
    st.write(report['next_manual_check'])
    st.caption(f"Planner: {report['planner']} · Model tokens: {report['model_tokens']}")
    st.download_button('Download investigation JSON',json.dumps(trace,indent=2),'datamedic-investigation.json','application/json')
else:
    st.info('The seeded demo uses Olist purchases on August 15, 2018, with synthetic ingestion evidence. Deterministic mode needs no API key.')
