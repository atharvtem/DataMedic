"""Conservative PostgreSQL SELECT subset. Unknown syntax fails closed."""
import sqlglot
from sqlglot import exp

COLUMNS = {
    'orders': {'order_id', 'order_status', 'order_purchase_timestamp'},
    'order_payments': {'order_id', 'payment_sequential', 'payment_type', 'payment_installments', 'payment_value'},
}
ALLOWED = set('Select From Table Identifier TableAlias Column Alias Literal Null Boolean Star Count Sum Avg Min Max Coalesce Distinct Where Group Having Order Ordered Limit Join EQ NEQ GT GTE LT LTE And Or Not Is Between In Paren Add Sub Mul Div Neg Case If'.split())

class PolicyError(ValueError):
    pass


def validate(query: str) -> str:
    if not query or len(query.encode()) > 16000:
        raise PolicyError('Query must contain 1–16000 bytes.')
    try:
        statements = sqlglot.parse(query, read='postgres')
    except sqlglot.errors.SqlglotError:
        raise PolicyError('Malformed PostgreSQL query.') from None
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise PolicyError('Exactly one SELECT is supported.')
    tree = statements[0]
    for node in tree.walk():
        if type(node).__name__ not in ALLOWED:
            raise PolicyError('Unsupported SQL construct; use a simple SELECT with approved aggregates.')
        if isinstance(node, exp.Star) and not isinstance(node.parent, exp.Count):
            raise PolicyError('Select explicit permitted columns; only COUNT(*) permits a wildcard.')
    aliases = {}
    for table in tree.find_all(exp.Table):
        if table.catalog or table.db != 'olist' or table.name not in COLUMNS:
            raise PolicyError('Only qualified, permitted olist tables are supported.')
        if table.alias_or_name in aliases:
            raise PolicyError('Use distinct table aliases.')
        aliases[table.alias_or_name] = table.name
    if not aliases or len(aliases) > 3:
        raise PolicyError('Use one to three permitted tables.')
    for col in tree.find_all(exp.Column):
        if col.db or col.catalog:
            raise PolicyError('Use table aliases for column qualification.')
        candidates = [aliases[col.table]] if col.table in aliases else list(aliases.values()) if not col.table else []
        if sum(col.name in COLUMNS[t] for t in candidates) != 1:
            raise PolicyError('Column is restricted, unknown, or ambiguous; use a qualified permitted column.')
    limit = tree.args.get('limit')
    if not limit or not isinstance(limit.expression, exp.Literal) or not limit.expression.is_int:
        raise PolicyError('Include a literal LIMIT between 1 and 200.')
    if not 1 <= int(limit.expression.this) <= 200:
        raise PolicyError('LIMIT must be between 1 and 200.')
    for node in tree.walk():
        node.comments = None
    return tree.sql(dialect='postgres', identify=True)
