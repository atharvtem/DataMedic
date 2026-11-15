import asyncio
import hashlib
import json
import streamlit as st
from datamedic.charts import render_chart
from datamedic.datasets import load_files,profile,suggestions,Plan,SYSTEM,execute
from datamedic.agent.llm import LLMPlanner
from datamedic.file_investigation import investigate_files


def render():
    st.title('DataMedic — check your files')
    st.write('Upload tables, choose a check, and review the findings. Your data is never changed.')
    st.caption('CSV and flat JSON supported. Up to 5 files, 20 MB total, 100,000 rows and 100 columns per table. Excel, PDFs and database connections are not supported in this workspace yet.')
    uploads=st.file_uploader('Upload your tables',type=['csv','json'],accept_multiple_files=True)
    if not uploads:
        st.info('Try a sales file, an inventory export, or two files with matching IDs. Each file becomes a table.')
        return
    files=[(f.name,f.getvalue()) for f in uploads]
    digest=hashlib.sha256()
    for name,data in files: digest.update(name.encode());digest.update(data)
    fingerprint=digest.hexdigest()
    if st.session_state.get('file_fingerprint')!=fingerprint:
        for key in ['file_tables','file_profile','file_plan','file_result','file_investigation']: st.session_state.pop(key,None)
        try:
            tables=load_files(files)
            st.session_state.update(file_tables=tables,file_profile=profile(tables),file_fingerprint=fingerprint)
        except Exception as exc:
            st.error(f'Could not read these files: {exc}')
            return
    tables=st.session_state['file_tables'];metadata=st.session_state['file_profile']
    st.subheader('1. What is in your data?')
    for name,t in metadata.items():
        with st.expander(f"{name} · {t['rows']:,} rows · {len(t['columns'])} columns"):
            st.dataframe(t['columns'],hide_index=True,width='stretch')
            st.caption('Types are suggestions based on up to 1,000 nonempty values. Checks run over all loaded rows. Blank cells count as missing; text such as NA is preserved.')
            st.dataframe(tables[name].head(10),hide_index=True,width='stretch')
    st.subheader('2. What do you want to check?')
    with st.form('file_request'):
        selected=st.multiselect('Suggested checks',suggestions(metadata))
        custom=st.text_area('Or write your own check','',placeholder='For example: Show monthly sales and check if customer IDs are missing from the customer file.')
        provider=st.selectbox('Agent',['groq','gemini'])
        follow_up=st.checkbox('Investigate results with follow-up checks',value=True)
        st.caption('Investigations use at most 4 planning rounds and 11 operations (8 checks and 3 charts).')
        st.caption('When you create a plan, the selected AI provider receives your request, file/column names, inferred types and counts. Follow-ups also send aggregate check statistics and chart status, but no chart cell values or example rows. Raw cell values stay in this app. Planning does not change your data.')
        submitted=st.form_submit_button('Create charts and check data',type='primary')
    if submitted:
        st.session_state.pop('file_plan',None);st.session_state.pop('file_result',None);st.session_state.pop('file_investigation',None)
        for key in list(st.session_state):
            if key.startswith(('hue-', 'filter-', 'measure-')): st.session_state.pop(key,None)
        if not selected and not custom.strip():
            st.warning('Choose a suggested check or write a question.')
        else:
            try:
                planner=LLMPlanner(provider)
                if follow_up:
                    progress=st.empty()
                    investigation=asyncio.run(investigate_files(tables,selected+[custom],planner,on_progress=progress.info))
                    progress.empty()
                    plan=investigation.plan
                    st.session_state['file_result']=(investigation.findings,investigation.charts)
                    st.session_state['file_investigation']={
                        'stop_reason':investigation.stop_reason,'steps':investigation.steps,
                        'planning_calls':investigation.calls,'history':investigation.history,
                        'planning_errors':investigation.planning_errors}
                else:
                    with st.spinner('Choosing relevant tables, columns and charts…'):
                        plan=asyncio.run(asyncio.wait_for(planner.generate({'request':selected+[custom], 'tables':metadata},Plan,system=SYSTEM),timeout=60))
                    st.session_state['file_result']=execute(tables,plan)
                st.session_state['file_plan']=plan.model_dump()
                st.session_state['file_request_text']=selected+[custom]
                st.session_state['file_result_plan']=plan.model_dump()
            except Exception:
                st.error('The agent could not create a valid plan. Check provider availability or quota, then retry. No checks have run and your data is unchanged.')
    if 'file_plan' not in st.session_state: return
    plan=Plan.model_validate(st.session_state['file_plan'])
    if investigation := st.session_state.get('file_investigation'):
        st.info(investigation['stop_reason'])
        with st.expander(f"Investigation history · {investigation['steps']} steps · {investigation['planning_calls']} planning calls"):
            st.json(investigation['history'])
            if investigation.get('planning_errors'):
                st.write('Planning errors (earlier results are retained):')
                st.json(investigation['planning_errors'])
    st.subheader('3. Analysis settings')
    st.write(plan.explanation)
    st.caption('Charts and checks run on your original data. No fixes are required. Each uploaded file is one table.')
    if plan.checks:
        st.dataframe([{'Dataset / table':c.table,'Columns':', '.join(c.columns) or 'All columns','Planned check':c.kind.replace('_',' '),'Purpose':c.reason} for c in plan.checks],hide_index=True,width='stretch')
    for i,c in enumerate(plan.charts):
        st.write(f"Chart: **{c.table}** · {c.kind} · {c.x}"+(f' / {c.y}' if c.y else '')+f' — {c.reason}')
        if c.table not in tables:
            st.warning(f'Table {c.table} is unavailable for this chart.')
            continue
        columns=list(tables[c.table].columns)
        c.color_by=st.selectbox(f'Colour groups · {i+1}',[None]+columns,index=([None]+columns).index(c.color_by) if c.color_by in columns else 0,format_func=lambda x:'No grouping' if x is None else x,key=f'hue-{i}')
        if c.kind in {'histogram','category','time'} and (c.kind=='histogram' or c.aggregation=='count'):
            measures={'none':'Row counts','all_rows':'Percentage of all usable rows'}
            if c.color_by:
                measures['within_series']='Percentage within each colour group'
                if c.kind!='histogram': measures['within_category']='Percentage within each category / time bucket'
            options=list(measures)
            c.normalization=st.selectbox(f'Show counts or percentages · {i+1}',options,index=options.index(c.normalization) if c.normalization in options else 0,format_func=measures.get,key=f'measure-{i}')
            st.caption('Percentages use rows remaining after filters and date bounds. The exact denominator is shown below the chart.')
        with st.expander(f'Filter chart · {i+1}'):
            c.filter_column=st.selectbox(f'Filter column · {i+1}',[None]+columns,index=([None]+columns).index(c.filter_column) if c.filter_column in columns else 0,format_func=lambda x:'No filter' if x is None else x,key=f'filter-col-{i}')
            if c.filter_column:
                op=st.selectbox(f'Filter type · {i+1}',['equals','not_equals','contains','greater_than','less_than','between'],index=['equals','not_equals','contains','greater_than','less_than','between'].index(c.filter_operator) if c.filter_operator in ['equals','not_equals','contains','greater_than','less_than','between'] else 0,key=f'filter-op-{i}')
                c.filter_operator=op
                c.filter_value=st.text_input(f'Filter value · {i+1}',c.filter_value or '',key=f'filter-val-{i}')
                if op=='between': c.filter_upper=st.text_input(f'Filter end value · {i+1}',c.filter_upper or '',key=f'filter-upper-{i}')
            else:
                c.filter_operator=c.filter_value=c.filter_upper=None
    with st.expander('Exact columns, date ranges and chart settings'): st.json(plan.model_dump())
    for message in plan.unsupported: st.warning('Not covered: '+message)
    if st.button('Update charts and checks',type='primary',disabled=not (plan.checks or plan.charts)):
        st.session_state.pop('file_investigation',None)
        st.session_state.pop('file_result',None)
        try:
            with st.spinner('Calculating results from your files…'):
                findings,charts=execute(tables,plan)
            st.session_state['file_result']=(findings,charts)
            st.session_state['file_result_plan']=plan.model_dump()
        except Exception as exc:
            st.error(f'This plan could not be executed: {exc}. Ask for a revised check. No data was changed.')
    if 'file_result' not in st.session_state: return
    findings,charts=st.session_state['file_result']
    if st.session_state.get('file_result_plan')!=plan.model_dump():
        st.info('Settings have changed. Click Update charts and checks to apply them. Results below show the previous run.')
    st.subheader('4. Your charts')
    for chart in charts:
        c=chart['spec'];frame=chart['data']
        st.write(f"**{c['table']} · {c['x']}**")
        if chart.get('error'):
            st.warning(f"Could not draw this chart: {chart['error']}")
            continue
        st.altair_chart(render_chart(chart),width='stretch')
        st.caption(chart['note'])
        with st.expander('Numbers behind this chart'): st.dataframe(frame,hide_index=True,width='stretch')
    st.subheader('5. Findings and suggested fixes')
    rows=[]
    for f in findings:
        details=f['details']
        if f.get('status')!='completed':
            amount='Not measured';issue=f['message']
        elif f['check']=='summary':
            amount=f"{details.get('valid_numbers',0):,} readable numbers";issue='Numeric summary (not an error)'
        else:
            amount=f"{f['rows_to_review']:,} of {f['rows_checked']:,} rows"
            issue=f['check'].replace('_',' ')
            if f['check']=='missing':
                issue='Missing cells: '+', '.join(f'{col}: {count:,}' for col,count in details.items())
        rows.append({'Dataset / table':f['table'],'Columns':', '.join(f['columns']) or 'All columns',
            'What needs review':issue,'How much':amount,'Suggested fix / next step':f['next_step']})
    if rows:
        st.dataframe(rows,hide_index=True,width='stretch')
        st.caption('Counts are measured from your files. Missing or unusual values are review candidates; they may be valid for your use case.')
        with st.expander('Check details and example row numbers'):
            for f in findings:
                st.write(f"**{f['table']} · {', '.join(f['columns'])} · {f['check'].replace('_',' ')}**")
                st.write(f['message'])
                if f['details']: st.json(f['details'])
                if f['example_row_numbers']: st.write('Example data-row numbers:',f['example_row_numbers'])
                st.caption(f['limit'])
    else: st.write('No data checks were completed in this run. Charts can be created independently of data checks.')
    st.subheader('What should you do next?')
    if not findings:
        st.write('No data-quality conclusion is available from this run. Review the stop reason and any uncovered parts above, or clarify your question.')
    elif any(f.get('status')=='failed' for f in findings):
        st.write('Some checks could not run. Review their next steps in the table; the available charts are still shown above.')
    elif any(f['rows_to_review'] for f in findings):
        st.write('Start with the rows listed in the table. Compare them with the original source and confirm whether they are errors before asking the data owner for a correction.')
    else:
        st.write('Review your charts or ask another question. No rows were flagged by the completed checks; this does not prove the whole dataset is correct.')
    st.caption('These are suggested actions only. This app never edits, deletes or repairs your records.')
    report={'request':st.session_state['file_request_text'],'files_sha256':fingerprint,'plan':st.session_state.get('file_result_plan',plan.model_dump()),
            'investigation':st.session_state.get('file_investigation'),'findings':findings,'charts':[{'spec':c['spec'],'note':c['note'],'error':c.get('error'),'values':json.loads(c['data'].to_json(orient='records'))} for c in charts]}
    st.download_button('Download findings report',json.dumps(report,indent=2,default=str),'datamedic-findings.json','application/json')
    st.caption('The report contains checks, counts, example row numbers, chart summaries and suggested next steps. It is not a corrected dataset.')
