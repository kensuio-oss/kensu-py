from psycopg2 import extras


def pg_result_to_dict(cur, res):
    rows=[]
    for row in res:
        row_dict = {}
        idx = 0
        for col in cur.description:
            row_dict.update({str(col.name): row[idx]})
            idx += 1
        rows.append(row_dict)
    return rows


def pg_query_as_dicts(cur, q):
    cur.execute(q)
    res = cur.fetchall()
    return pg_result_to_dict(cur, res)


def get_current_db_info(cur):
    res=pg_query_as_dicts(cur, q='SELECT current_database() AS curr_catalog, current_schema() AS curr_schema')
    for r in res:
        return r.get('curr_catalog'), r.get('curr_schema')
    return None, None

def get_table_schema(cur, table_name):
    # returns [{'field_name': 'start_date', 'field_type': 'date'}]

    cur.execute("select * from {} where false".format(table_name))
    fields_with_typeid = [[col.name, col.type_code] for col in cur.description]

    # below it generates query like this
    # SELECT q.field_name, q.field_type_oid, format_type(q.field_type_oid, NULL)
    # FROM (VALUES ('int', 20), ('dt', 1082)) AS q(field_name, field_type_oid);
    q = """SELECT q.field_name, format_type(q.field_type_oid, NULL) AS field_type
            FROM (VALUES %s) AS q(field_name, field_type_oid)"""
    result = extras.execute_values(cur, q, fields_with_typeid, fetch=True)
    res_dict = pg_result_to_dict(cur=cur, res=result)
    return res_dict
