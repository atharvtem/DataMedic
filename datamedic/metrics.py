"""Transparent comparison of recorded payments by purchase date."""
from datetime import timedelta
from decimal import Decimal


def summarize(day, result):
    if result.get('ok') is not True:
        raise ValueError('Could not read payment metrics. Check the database service.')
    observed = {r[0]:dict(zip(result['columns'],r)) for r in result['rows']}
    days=[]
    for offset in range(-7,1):
        label=(day+timedelta(days=offset)).isoformat()
        row=observed.get(label,{})
        orders=int(row.get('orders',0)); paid=int(row.get('paid_orders',0))
        days.append(dict(date=label,orders=orders,paid_orders=paid,
            missing_orders=orders-paid,payment_value=Decimal(str(row.get('payment_value',0))),
            coverage=100*paid/orders if orders else None,has_orders=bool(orders)))
    average=sum(r['payment_value'] for r in days[:7])/7
    target=days[-1]
    change=(target['payment_value']/average-1)*100 if average else None
    return dict(days=days,target=target,average=average,change=change,
                complete=all(r['has_orders'] for r in days))
