"""Render calculated chart data with independent axes and color encodings."""
import json
from decimal import Decimal, InvalidOperation
import altair as alt


def category_order(values):
    """Order numeric labels by value, preserving the original category labels."""
    labels=list(dict.fromkeys(str(value) for value in values))
    try:
        numbers={label:Decimal(label) for label in labels}
        if all(value.is_finite() for value in numbers.values()):
            return sorted(labels,key=lambda label:(numbers[label],label))
    except InvalidOperation:
        pass
    return sorted(labels,key=lambda label:(label.casefold(),label))


def category_axis(values, title):
    labels=category_order(values)
    short=max((len(label) for label in labels),default=0)<=5
    return dict(title=title,sort=labels,axis=alt.Axis(labelAngle=0 if short else -35,labelOverlap=False))


def render_chart(result):
    c=result['spec']
    frame=result['data']
    # Explicit inline data avoids Altair's implicit 5,000-row transformer limit.
    frame=frame.copy()
    if c['kind']=='time': frame['date_label']=frame['group'].str[:10]
    data=alt.Data(values=json.loads(frame.to_json(orient='records')))
    base=alt.Chart(data)
    domain=category_order(result.get('color_domain') or (frame['series'] if 'series' in frame else frame['group'] if c['kind']=='histogram' else []))
    scale=alt.Scale(domain=domain,scheme='tableau10')
    color={'color':alt.Color('series:N',title=c['color_by'],sort=domain,scale=scale)} if c.get('color_by') and 'series' in frame else {}
    percent=c.get('normalization','none')!='none'
    label={'all_rows':'% of usable rows','within_series':'% within colour group','within_category':'% within time bucket' if c['kind']=='time' else '% within category'}.get(c.get('normalization'),'Rows')
    value='share:Q' if percent else 'value:Q'
    value_axis=alt.Axis(format='.0%' if percent else '~s')
    value_scale=alt.Scale(domain=[0,1]) if percent else alt.Scale(zero=True)
    extra=[alt.Tooltip('share:Q',title='Share',format='.2%'),'denominator:Q'] if percent else []
    if c['kind']=='histogram':
        return base.mark_bar(opacity=.55).encode(
            x=alt.X('lower:Q',title=c['x']),x2='upper:Q',
            y=alt.Y('share:Q' if percent else 'rows:Q',title=label,stack=None,axis=value_axis,scale=value_scale),
            color=alt.Color('group:N',title=c.get('color_by') or 'Group',sort=domain,scale=scale),
            tooltip=['range:N','group:N','rows:Q']+extra).interactive()
    if c['kind']=='scatter':
        return base.mark_circle(opacity=.65,size=45).encode(
            x=alt.X('x:Q',title=c['x'],scale=alt.Scale(zero=False)),y=alt.Y('y:Q',title=c['y'],scale=alt.Scale(zero=False)),
            tooltip=['x:Q','y:Q']+(['series:N'] if color else []),**color).interactive()
    if c['kind']=='box':
        labels=category_order(frame['x'])
        horizontal=len(labels)>12 or max(map(len,labels),default=0)>12
        category='y' if horizontal else 'x'
        measure='x' if horizontal else 'y'
        axis=alt.Y('x:N',title=c['x'],sort=labels,axis=alt.Axis(labelLimit=240)) if horizontal else alt.X('x:N',**category_axis(frame['x'],c['x']))
        enc={category:axis,**color}
        if color:
            enc[category+'Offset']=alt.YOffset('series:N',sort=domain) if horizontal else alt.XOffset('series:N',sort=domain)
        base=base.encode(**enc)
        position=alt.X if horizontal else alt.Y
        numeric=lambda field:position(field+':Q',title=c['y'],scale=alt.Scale(zero=False))
        whisker=base.mark_rule().encode(**{measure:numeric('low'),measure+'2':'high:Q'})
        box=base.mark_bar(size=12,opacity=.6).encode(**{measure:numeric('q1'),measure+'2':'q3:Q'},
            tooltip=['x:N']+(['series:N'] if color else [])+['low:Q','q1:Q','median:Q','q3:Q','high:Q','rows:Q'])
        median=base.mark_tick(size=12,orient='vertical' if horizontal else 'horizontal').encode(**{measure:numeric('median')})
        count=frame['series'].nunique() if color else 1
        height=max(300,len(labels)*max(28,16*count)) if horizontal else 340
        return (whisker+box+median).properties(height=height).interactive()
    time=c['kind']=='time'
    value_title=label if percent or c['aggregation']=='count' else f"{c['aggregation']} of {c['y']}"
    numeric=alt.Y(value,title=value_title,stack=None,axis=value_axis,scale=value_scale)
    enc={'x':alt.X('group:T',title=c['x']+' (UTC)',scale=alt.Scale(type='utc'),axis=alt.Axis(format='%b %Y' if c['period']=='MS' else '%b %d, %Y',tickCount='month' if c['period']=='MS' and frame['group'].nunique()<=24 else 8,labelOverlap=True)) if time else alt.X('group:N',**category_axis(frame['group'],c['x'])),
         'y':numeric,
         'tooltip':[alt.Tooltip('date_label:N',title=c['x']+' (UTC)') if time else alt.Tooltip('group:N',title=c['x']),alt.Tooltip('value:Q',title='Rows' if c['aggregation']=='count' else value_title)]+extra+(['series:N'] if color else []),**color}
    labels=category_order(frame['group'])
    horizontal=not time and (len(labels)>12 or max(map(len,labels),default=0)>12)
    if horizontal:
        enc['y']=alt.Y('group:N',title=c['x'],sort=labels,axis=alt.Axis(labelLimit=240))
        enc['x']=alt.X(value,title=value_title,stack=None,axis=value_axis,scale=value_scale)
    if color and not time:
        enc['yOffset' if horizontal else 'xOffset']=alt.YOffset('series:N',sort=domain) if horizontal else alt.XOffset('series:N',sort=domain)
    if time: enc['order']=alt.Order('group:T')
    mark=base.mark_line(point=True,invalid='break-paths-show-domains') if time else base.mark_bar()
    chart=mark.encode(**enc)
    if horizontal:
        # Give each category/series its own row instead of squeezing labels.
        count=frame['series'].nunique() if color else 1
        chart=chart.properties(height=max(300,len(labels)*max(26,12*count)))
    else: chart=chart.properties(height=340)
    return chart.interactive()
