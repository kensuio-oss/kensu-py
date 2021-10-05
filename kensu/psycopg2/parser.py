import logging
import traceback
import uuid

from pglast import parse_sql, ast

from kensu.pandas import KensuPandasSupport
from kensu.utils.dsl.extractors.external_lineage_dtos import KensuDatasourceAndSchema, ExtDependencyEntry, \
    GenericComputedInMemDs
from kensu.psycopg2.pghelpers import get_table_schema, get_current_db_info


def parse_and_report(cur,
                     final_sql,
                     argslist  # type: list
                     ):
    try:
        # FIXME: bytes decoding might give some issues...
        final_sql = final_sql.decode(cur.connection.encoding)
        cur_catalog, cur_schema = get_current_db_info(cur)

        for stmt in parse_sql(final_sql):
            if isinstance(stmt, ast.RawStmt):
                stmt = stmt.stmt
                if isinstance(stmt, ast.InsertStmt):
                    parse_insert(cur, cur_catalog, cur_schema, stmt, argslist=argslist)
                elif isinstance(stmt, ast.UpdateStmt):
                    parse_update(cur, cur_catalog, cur_schema, stmt, argslist=argslist)
                else:
                    logging.info("Kensu - met a not yet supported SQL statement:")
                    logging.info("Kensu - not yet supported SQL statement:" + str(stmt) + "SQL: " + final_sql)
    except:
        logging.warning("Failed parsing a SQL statement")
        traceback.print_exc()
        traceback.print_stack()


def parse_update(cur, cur_catalog, cur_schema, stmt, argslist):
    out_table_qualified_name = format_relation_name(stmt.relation, cur_catalog=cur_catalog, cur_schema=cur_schema)
    if stmt.targetList:
        explicit_column_names = [c.name for c in stmt.targetList]
    else:
        explicit_column_names = []

    out_stats_data_pandas = None
    # explicit param_field_names of those inside argslist
    if stmt.fromClause and stmt.fromClause[0].alias and stmt.fromClause[0].alias.colnames:
        # FIXME: take union of out_columns & param_field_names
        argslist_columns = [c.val for c in stmt.fromClause[0].alias.colnames]
        #print('argslist_columns', argslist_columns)
        out_stats_data_pandas=datastats_data(argslist_columns, argslist)
        # FIXME: and here we probably need to filter only columns used in UPDATE SET clause

    # if unable to figure out, assume write columns to be all the columns
    out_columns = schema_of_used_cols_or_all(cur, stmt.relation, explicit_column_names)
    report_write((out_table_qualified_name, out_columns),
                 op_type='psycopg2 update',
                 out_stats_data_pandas=out_stats_data_pandas,
                 inputs=None)


def schema_of_used_cols_or_all(cur, relation, explicit_column_names):
    if not explicit_column_names:
        explicit_column_names = []
    orig_out_table_name = format_relation_name(relation)
    out_table_schema = get_table_schema(cur, orig_out_table_name)
    if explicit_column_names:
        out_columns = [c for c in out_table_schema
                       if c['field_name'] in explicit_column_names]
    else:
        out_columns = out_table_schema
    return out_columns


def datastats_data(columns, argslist):
    import pandas as pd_orig
    # data = [['tom', 10], ['nick', 15], ['juli', 14]]
    try:
        if len(argslist) == 0 or len(argslist[0]) != len(columns):
            logging.warning("Kensu - failed converting argslist to pandas.DataFrame: columns count do not match")
            # print("columns: {}\n arglist item: {}".format(columns, argslist[0]))
            return None
        else:
            return pd_orig.DataFrame(argslist, columns=columns)
    except:
        logging.warning("Kensu - failed converting argslist to pandas.DataFrame")
        traceback.print_stack()
        return None

def parse_insert(cur, cur_catalog, cur_schema, stmt, argslist):
    out_table_qualified_name = format_relation_name(stmt.relation, cur_catalog=cur_catalog, cur_schema=cur_schema)
    if stmt.cols:  # 'INSERT INTO table_name(column1, column2) VALUES ...'
        explicit_column_names = [c.name for c in stmt.cols]
    else: # 'INSERT INTO table_name  VALUES ...'
        explicit_column_names = []
    out_columns = schema_of_used_cols_or_all(cur, stmt.relation, explicit_column_names)
    # here out_columns are also columns of argslist
    report_write((out_table_qualified_name, out_columns),
                 op_type='psycopg2 insert',
                 out_stats_data_pandas=datastats_data(columns = [c['field_name'] for c in out_columns],
                                                      argslist=argslist),
                 inputs=None)


def format_relation_name(relation, cur_catalog=None, cur_schema=None):
    parts = [
        relation.catalogname or cur_catalog,
        relation.schemaname or cur_schema,
        relation.relname
    ]
    return '.'.join([n for n in parts if n])


def report_write(out_table, op_type, out_stats_data_pandas, inputs=None):
    # FIXME: logical name etc?
    from kensu.utils.kensu_provider import KensuProvider
    ksu = KensuProvider().instance()
    if not inputs and len(ksu.inputs_ds)>0:
        inputs=ksu.inputs_ds

    if not inputs:
        input_path = 'in-mem://'+str(uuid.uuid4())
        input_ds = KensuDatasourceAndSchema.for_path_with_opt_schema(ksu=ksu,
                                                                     ds_path=input_path,
                                                                     maybe_schema=[("unknown", "unknown")],
                                                                     ds_name=input_path,
                                                                     f_get_stats=None)
        inputs = [input_ds]

    dest_name, out_schema = out_table
    dest_path = 'postgres://{}'.format(dest_name)
    if out_schema is None:
        out_schema = [("unknown", "unknown")]
    else:
        out_schema = [(f.get('field_name') or 'unknown', f.get('field_type') or 'unknown') for f in out_schema]
    f_get_stats =lambda: None  # no stats by default
    if out_stats_data_pandas is not None:
        f_get_stats = lambda: KensuPandasSupport().extract_stats(out_stats_data_pandas)
    output_ds = KensuDatasourceAndSchema.for_path_with_opt_schema(ksu=ksu,
                                                                  ds_path=dest_path,
                                                                  maybe_schema=out_schema,
                                                                  ds_name=dest_name,
                                                                  f_get_stats=f_get_stats,
                                                                  format='postgres table')


    lineage_info = [
        ExtDependencyEntry(
        input_ds=input_ds,
            # all to all lineage
        lineage=dict([(str(out_fieldname), [in_field for in_field in input_ds.field_names()])
                      for (out_fieldname, dtype) in out_schema]))
        for input_ds in inputs
    ]
    inputs_lineage = GenericComputedInMemDs(inputs=inputs, lineage=lineage_info)
    # register lineage in KensuProvider, if any
    inputs_lineage.report(ksu=ksu,
                          df_result=output_ds,
                          operation_type=op_type,
                          report_output=True,
                          register_output_orig_data=True  # FIXME?
                          )
    if lineage_info:
        # actuly report the lineage and the write operation to the sink
        ksu.report_with_mapping()
