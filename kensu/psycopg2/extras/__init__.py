from kensu.psycopg2.parser import parse_and_report
from psycopg2.extras import *
import psycopg2

# FIXME: now it's copy paste now, but we kinda need that...
def execute_values(cur, sql, argslist, template=None, page_size=100, fetch=False):
    orig_sql = sql
    orig_template = template
    from psycopg2.sql import Composable
    if isinstance(sql, Composable):
        sql = sql.as_string(cur)

    # we can't just use sql % vals because vals is bytes: if sql is bytes
    # there will be some decoding error because of stupid codec used, and Py3
    # doesn't implement % on bytes.
    if not isinstance(sql, bytes):
        from psycopg2 import extensions as _ext
        sql = sql.encode(_ext.encodings[cur.connection.encoding])
    from psycopg2.extras import _split_sql
    pre, post = _split_sql(sql)

    result = [] if fetch else None
    from psycopg2.extras import _paginate
    # kensu added start
    reported = False
    argslist = list(argslist)  # this might be iterator, and it'd break if accessed multiple times
    # end added
    for page in _paginate(argslist, page_size=page_size):
        if template is None:
            template = b'(' + b','.join([b'%s'] * len(page[0])) + b')'
        parts = pre[:]
        for args in page:
            parts.append(cur.mogrify(template, args))
            parts.append(b',')
        parts[-1:] = post

        # cur.execute(b''.join(parts))
        # if fetch:
        #     result.extend(cur.fetchall())
        # call original function for querying db and returning result
        result = psycopg2.extras.execute_values(cur, orig_sql, argslist, template=orig_template, page_size=page_size, fetch=fetch)

        # kensu added start
        if not reported:  # report only first page
            reported = True
            parse_and_report(cur, b''.join(parts), argslist)
        # added - end

    return result

execute_values.__doc__ = psycopg2.extras.execute_values.__doc__
