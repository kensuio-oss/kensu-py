from kensu.psycopg2.parser import parse_and_report
from psycopg2.extras import *
import psycopg2
from psycopg2.extras import _split_sql, _paginate

# FIXME: now it's copy paste now, but we kinda need that...
def execute_values(cur, sql, argslist, template=None, page_size=100, fetch=False):
    # kensu modifications start
    argslist = list(argslist)  # this might be iterator, and it'd break if accessed multiple times
    # call original function for querying db and returning result
    result = psycopg2.extras.execute_values(cur, sql, argslist, template=template, page_size=page_size,
                                            fetch=fetch)

    # below is mostly original code from psycopg2.extras.execute_values
    # - extract the first query (of possible multiple ones), and feed it to postgres SQL parser
    from psycopg2.sql import Composable
    if isinstance(sql, Composable):
        sql = sql.as_string(cur)

    # we can't just use sql % vals because vals is bytes: if sql is bytes
    # there will be some decoding error because of stupid codec used, and Py3
    # doesn't implement % on bytes.
    if not isinstance(sql, bytes):
        from psycopg2 import extensions as _ext
        sql = sql.encode(_ext.encodings[cur.connection.encoding])

    pre, post = _split_sql(sql)

    first_sql_query_bytes = None
    for page in _paginate(argslist, page_size=page_size):
        if template is None:
            template = b'(' + b','.join([b'%s'] * len(page[0])) + b')'
        parts = pre[:]
        for args in page:
            parts.append(cur.mogrify(template, args))
            parts.append(b',')
        parts[-1:] = post
        first_sql_query_bytes = b''.join(parts)
        break

    if first_sql_query_bytes is not None:
        parse_and_report(cur, first_sql_query_bytes, argslist)

    return result

execute_values.__doc__ = psycopg2.extras.execute_values.__doc__
