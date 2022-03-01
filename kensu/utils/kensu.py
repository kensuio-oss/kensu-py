import datetime
import getpass
import json
import logging
import os
import time
import jwt

from kensu.client import *
from kensu.utils.dsl.extractors.external_lineage_dtos import KensuDatasourceAndSchema
from kensu.utils.dsl import mapping_strategies
from kensu.utils.dsl.extractors import Extractors
from kensu.utils.dsl.lineage_builder import LineageBuilder
from kensu.utils.helpers import to_hash_key
from kensu.utils.injection import Injection
from kensu.pandas import DataFrame,Series
from kensu.utils.reporters import *
from kensu.utils.rule_engine import create_kensu_nrows_consistency
from kensu import sdk


class Kensu(object):
    UNKNOWN_PHYSICAL_LOCATION = PhysicalLocation(name="Unknown", lat=0.12341234, lon=0.12341234,
                                                 pk=PhysicalLocationPK(city="Unknown", country="Unknown"))

    @staticmethod
    def discover_user_name():
        return getpass.getuser()

    @staticmethod
    def get_git_repo():
        cur_dir = os.path.realpath(os.path.curdir)
        try:
            import git
            try:
                git_repo = git.Repo(cur_dir, search_parent_directories=True)
                return git_repo
            except git.GitError as e:
                logging.warning("kensu-py was unable to identify a git repo. The working dir is not a git repo?")
                pass
        except ImportError as e:
            logging.warning("Install GitPython for a maximum context about the GIT code repo if any")
            pass

    @staticmethod
    def discover_code_location():
        cur_dir = os.path.realpath(os.path.curdir)
        code_location = cur_dir
        git_repo = Kensu.get_git_repo()
        if git_repo is not None:
            remote = git_repo.remote()
            code_location = next(remote.urls, code_location)
        return code_location

    @staticmethod
    def discover_code_version():
        code_version = datetime.datetime.now().isoformat()

        git_repo = Kensu.get_git_repo()
        if git_repo is not None:
            code_version = git_repo.head.commit.hexsha
            if git_repo.is_dirty():
                code_version = code_version + " (dirty)"
        return code_version

    @staticmethod
    def get_conf_path(self, default = "conf.ini"):
        return os.environ["CONF_FILE"] if "CONF_FILE" in os.environ else default

    @staticmethod
    def build_conf():
        """
        Returns configparser.ConfigParser
        """
        from configparser import ConfigParser, ExtendedInterpolation
        config = ConfigParser(interpolation=ExtendedInterpolation())
        conf_path = Kensu.get_conf_path("conf.ini")
        try:
            config.read(conf_path)
        except:
            logging.warning(f"Cannot load config from file `%s`" % (conf_path))
        return config

    def __init__(self, api_url=None, auth_token=None, process_name=None,
                 user_name=None, code_location=None, init_context=True, 
                 do_report=None, report_to_file=None, offline_file_name=None, 
                 compute_stats=True, 
                 config=None, **kwargs):
        """
        config: : configparser.ConfigParser if None `build_conf` will be tried
        """
        if config is None:
            config = Kensu.build_conf()

        kensu_conf = config['kensu'] if config.has_section('kensu') else config['DEFAULT']
        self.conf = kensu_conf

        kensu_host = self.get_kensu_host(api_url)
        if kensu_host is None:
            kensu_host = kensu_conf.get("api_url")
        if auth_token is None:
            kensu_auth_token = kensu_conf.get("api_token")
        else:
            kensu_auth_token = auth_token

        # returns a value following this precedence:
        #   kwargs = arg > conf > default
        # default is used to determine the type of the conf value (it can be overriden by tpe)
        def kwargs_or_conf_or_default(key, default, arg=None, kw=kwargs, conf=kensu_conf, tpe=None):
            if arg is not None:
                return arg
            elif key in kw and kw[key] is not None:
                return kw[key]
            elif key in conf and conf.get(key) is not None:
                if default is not None and tpe is None:
                    tpe = type(default)
                r = conf.get(key)
                if tpe is list:
                    r = r.split(",")
                elif tpe is bool:
                    r = conf.getboolean(key)
                elif tpe is not None:
                    r = tpe(r)
                return r
            else:
                return default
        self.extractors = Extractors()
        pandas_support = kwargs_or_conf_or_default("pandas_support", True)
        sklearn_support = kwargs_or_conf_or_default("sklearn_support", False)
        bigquery_support = kwargs_or_conf_or_default("bigquery_support", False)
        tensorflow_support = kwargs_or_conf_or_default("tensorflow_support", False)
        matplotlib_support = kwargs_or_conf_or_default("matplotlib_support", False)

        self.extractors.add_default_supports(pandas_support=pandas_support, sklearn_support=sklearn_support,bigquery_support=bigquery_support,tensorflow_support=tensorflow_support, matplotlib_support = matplotlib_support)

        bigquery_headers = kwargs_or_conf_or_default("bigquery_headers", None)
        if bigquery_headers:
            self.bigquery_headers = bigquery_headers

        project_names = kwargs_or_conf_or_default("project_names", [])
        environment = kwargs_or_conf_or_default("environment", None)
        timestamp = kwargs_or_conf_or_default("timestamp", None, tpe=int)
        logical_naming = kwargs_or_conf_or_default("logical_naming", None)
        mapping = kwargs_or_conf_or_default("mapping", None)
        report_in_mem = kwargs_or_conf_or_default("report_in_mem", False)
        sql_util_url = kwargs_or_conf_or_default("sql_util_url", None)

        if "get_code_version" in kwargs and kwargs["get_code_version"] is not None:
            get_code_version = kwargs["get_code_version"]
        else:
            get_code_version = Kensu.discover_code_version

        process_name = kwargs_or_conf_or_default("process_name", "Missing Application Name", process_name)
        user_name = kwargs_or_conf_or_default("user_name", "Missing User Name", user_name)
        code_location = kwargs_or_conf_or_default("code_location", None, code_location)

        reporter = kwargs_or_conf_or_default('reporter', None)
        do_report = kwargs_or_conf_or_default("do_report", True, do_report)
        report_to_file = kwargs_or_conf_or_default("report_to_file", False, report_to_file)
        offline_file_name = kwargs_or_conf_or_default("offline_file_name", None, offline_file_name)
        compute_stats = kwargs_or_conf_or_default("compute_stats", True, compute_stats)
        input_stats = kwargs_or_conf_or_default("input_stats", True)
        compute_delta = kwargs_or_conf_or_default("compute_delta",False)
        if compute_delta and not input_stats:
            logging.warning("delta nrows stats (compute_delta=True) will not work without setting input_stats=True")
        raise_on_check_failure = kwargs_or_conf_or_default("raise_on_check_failure", False)

        self.kensu_api = KensuEntitiesApi()
        self.kensu_api.api_client.host = kensu_host
        self.kensu_api.api_client.default_headers["X-Auth-Token"] = kensu_auth_token
        self.api_url = kwargs_or_conf_or_default("api_url", None)
        self.report_to_file = report_to_file

        sdk_pat = kwargs_or_conf_or_default("PAT", None)
        sdk_url = kwargs_or_conf_or_default("sdk_url", None)
        sdk_verify_ssl = kwargs_or_conf_or_default("sdk_verify_ssl", True)
        if sdk_pat is None:
            self.sdk = sdk.DoNothingSDK()
        else:
            if sdk_url is None:
                sdk_url = self.api_url.replace('-api', '')                
            self.sdk = sdk.SDK(sdk_url, sdk_pat, verify_ssl=sdk_verify_ssl)


        # add function to Kensu entities
        injection = Injection()

        # reporter could be either an instance of Reporter already, or None, or a String (the class name of the reporter)
        if isinstance(reporter, str) or config.has_section('kensu.reporter'):
            reporter = Reporter.create(config['kensu.reporter'], reporter)
        elif reporter is not None and hasattr(reporter, '__call__'):
            reporter = GenericReporter(config, reporter.__call__)

        injection.set_reporter(reporter)
        injection.set_do_report(do_report, offline_file_name=offline_file_name, report_to_file=report_to_file)
        injection.set_kensu_api(self.kensu_api)

        self.logical_naming = logical_naming
        self.mapping = mapping
        self.report_in_mem = report_in_mem
        self.compute_stats = compute_stats
        self.compute_delta = compute_delta
        self.raise_on_check_failure = raise_on_check_failure
        self.offline_file_name = offline_file_name
        self.sql_util_url = sql_util_url
        self.input_stats = input_stats

        self.set_default_physical_location(Kensu.UNKNOWN_PHYSICAL_LOCATION)
        # can be updated using set_default_physical_location
        self.init_context(process_name=process_name, user_name=user_name, code_location=code_location,
                          get_code_version=get_code_version, project_names=project_names, environment=environment, timestamp=timestamp)

    # sets the api url using host if passed, otherwise gets KENSU_API_URL
    def get_kensu_host(self, host=None):
        if host is None:
            if "KENSU_API_URL" in os.environ:
                kensu_host = os.environ["KENSU_API_URL"]
            else:
                kensu_host = None
        else:
            kensu_host = host

        return kensu_host

    def register_schema_name(self, ds, schema):
        name = ds.name
        if "in-mem" in name and ds.format is not None:
            name = name + " of format=" + str(ds.format or '?')
        self.schema_name_by_guid[schema.to_guid()] = name
        try:
            self.logical_name_by_guid[schema.to_guid()] = ds.categories[0].split("::")[1]
        except:
            None
        return schema

    def to_schema_name(self, s_guid):
        return self.schema_name_by_guid.get(s_guid) or s_guid

    def to_schema_names(self, s_guids):
        return list(set([self.to_schema_name(s_guid) for s_guid in s_guids]))

    def init_context(self, process_name=None, user_name=None, code_location=None, get_code_version=None, project_names=None,environment=None,timestamp=None):
        # list of triples i, o, mapping strategy
        # i and o are either one or a list of triples (object, DS, SC)
        self.dependencies = []
        self.dependencies_mapping = []
        self.dependencies_per_columns = {}
        # when set, it seems to indicate if a schema/DS is a real one (is not in memory),
        # so must be not set for in memory DSes
        self.real_schema_df = {}
        self.schema_name_by_guid = {}
        self.logical_name_by_guid = {}
        # by lineage_id, thus this tracks for which lineages a lineage run was already sent
        self.sent_runs = []
        self.data_collectors = {}
        self.model={}
        self.set_timestamp(timestamp)
        self.inputs_ds = []
        self.lineage_and_ds = {}
        self.write_reinit = False
        self.rules = []
        self.check_rules = []
        self.schema_stats = {}
        self.stats_to_send={}

        if user_name is None:
            user_name = Kensu.discover_user_name()
        if code_location is None:
            code_location = Kensu.discover_code_location()
        self.user = User(pk=UserPK(user_name))._report()
        self.code_base = CodeBase(pk=CodeBasePK(code_location))._report()
        if get_code_version is None:
            if timestamp is not None: # this is weird though...
                version = datetime.datetime.fromtimestamp(timestamp/1000).isoformat()
            else:
                version = Kensu.discover_code_version()
        else:
            version = get_code_version()
        self.code_version = CodeVersion(maintainers_refs=[self.user.to_ref()],
                                        pk=CodeVersionPK(version=version,
                                                         codebase_ref=self.code_base.to_ref()))._report()
        if process_name is None:
            if "__file__" in globals():
                process_name = os.path.basename(os.path.realpath(__file__))
            else:
                raise Exception("Can't determine `process_name`, maybe is this running from a Notebook?")
        self.process = Process(pk=ProcessPK(qualified_name=process_name))._report()
        if project_names is None:
            self.project_refs = []
        else:
            self.project_refs = [Project(pk=ProjectPK(name=n))._report().to_ref() for n in project_names]
        process_run_name = process_name + "@" + datetime.datetime.now().isoformat()
        self.process_run = ProcessRun(
            pk=ProcessRunPK(process_ref=self.process.to_ref(), qualified_name=process_run_name)
            , launched_by_user_ref=self.user.to_ref()
            , executed_code_version_ref=self.code_version.to_ref()
            , projects_refs=self.project_refs
            , environment = environment
        )._report()

    def set_reinit(self, bool = True):
        self.write_reinit = bool

    def add_input_ref(self, entities):
        if self.write_reinit == True:
            self.inputs_ds = []
            self.write_reinit = False
        self.inputs_ds.append(entities)

    def set_timestamp(self, timestamp):
        if timestamp is not None:
            self.kensu_api.api_client.default_headers["X-Entity-Creation-Time"] = timestamp
        else:
            timestamp = datetime.datetime.now().timestamp()*1000
        self.timestamp = timestamp

    def set_default_physical_location(self, pl):
        self.default_physical_location = pl
        pl._report()
        self.default_physical_location_ref = pl.to_ref()

    def get_dependencies_mapping(self):
        return self.dependencies_mapping

    def add_dependencies_mapping(self, guid, col, from_guid, from_col, type):
        dep = {'GUID': guid,
               'COLUMNS': col,
               'FROM_ID': from_guid,
               'FROM_COLUMNS': from_col,
               'TYPE': type}
        self.dependencies_mapping.append(dep)

    def in_mem(self, var_name):
        return "in-memory-data://" + self.process.pk.qualified_name + "/" + var_name

    def name_for_stats(self, input_name):
        return input_name.replace('.', '_')

    def extract_stats(self, stats_df):
        try:
            stats = self.extractors.extract_stats(stats_df)
        except Exception as e:
            logging.warning(f'stats extraction from {type(stats_df)} failed', e)
            if isinstance(stats_df, dict):
                # FIXME: this is weird logic here... we'd post the actual data instead of stats!
                stats = stats_df
            else:
                # TODO Support ndarray
                stats = None
        return stats


    def report_with_mapping(self):
        self.set_reinit()
        import pandas as pd
        deps = self.dependencies_mapping
        ddf = pd.DataFrame(deps)
        df = ddf.set_index(['GUID', 'COLUMNS', 'FROM_ID']).groupby(['GUID', 'COLUMNS', 'FROM_ID']).agg(list)
        df = df[~df.index.duplicated(keep='first')].reset_index()

        unique_ids = list(df['GUID'].unique())

        if self.report_in_mem:
            #TODO Deprecate
            for element in unique_ids:
                dataflow = []
                dependencies = df[df['GUID'] == element]
                data = {}
                for row in dependencies.iterrows():
                    info = row[1]
                    from_columns = [str(x) for x in info['FROM_COLUMNS']]
                    data[str(info['COLUMNS'])] = from_columns
                schema_dep = SchemaLineageDependencyDef(from_schema_ref=SchemaRef(by_guid=info['FROM_ID']),
                                                        to_schema_ref=SchemaRef(by_guid=info['GUID']),
                                                        column_data_dependencies=data)
                dataflow.append(schema_dep)

                lineage = ProcessLineage(name=self.get_lineage_name(dataflow),
                                         operation_logic='APPEND',
                                         pk=ProcessLineagePK(process_ref=ProcessRef(by_guid=self.process.to_guid()),
                                                             data_flow=dataflow))._report()

                if lineage.to_guid() not in self.sent_runs:
                    lineage_run = LineageRun(pk=LineageRunPK(lineage_ref=ProcessLineageRef(by_guid=lineage.to_guid()),
                                                             process_run_ref=ProcessRunRef(
                                                                 by_guid=self.process_run.to_guid()),
                                                             timestamp=round(self.timestamp)))._report()
                    self.sent_runs.append(lineage.to_guid())
        else:
            dependencies_per_columns = {}
            for element in unique_ids:
                if element in self.real_schema_df:
                    sub_df = df[df['GUID'] == element]
                    for row in sub_df.iterrows():
                        info = row[1]
                        destination_guid = info['GUID']
                        guid = info['GUID']
                        origin_column = info['COLUMNS']
                        column = info['COLUMNS']
                        all_deps = df
                        self.create_dependencies(destination_guid, guid, origin_column, column, all_deps,
                                            dependencies_per_columns)

            dataflows = {}
            for destination_guid in dependencies_per_columns:
                if dependencies_per_columns[destination_guid] != {}:
                    dataflows[destination_guid] = {}
                    for column in dependencies_per_columns[destination_guid]:
                        for origin_guid in dependencies_per_columns[destination_guid][column]:
                            if origin_guid not in dataflows[destination_guid] and origin_guid!=destination_guid:
                                dataflows[destination_guid][origin_guid] = {}
                                dataflows[destination_guid][origin_guid][column]=list(set(dependencies_per_columns[destination_guid][column][origin_guid]))
                            elif origin_guid!=destination_guid:
                                dataflows[destination_guid][origin_guid][column] = \
                                list(set(dependencies_per_columns[destination_guid][column][origin_guid]))

            for to_guid in dataflows:
                schemas_pk = set()
                from_pks = set()
                dataflow = []
                is_ml_model = False
                for from_guid in dataflows[to_guid]:

                    schema_dep = SchemaLineageDependencyDef(from_schema_ref=SchemaRef(by_guid=from_guid),
                                                            to_schema_ref=SchemaRef(by_guid=to_guid),
                                                            column_data_dependencies=dataflows[to_guid][from_guid])
                    if to_guid in self.model:
                        is_ml_model = True
                    dataflow.append(schema_dep)
                    schemas_pk.add(from_guid)
                    from_pks.add(from_guid)
                    schemas_pk.add(to_guid)


                lineage = ProcessLineage(name=self.get_lineage_name(dataflow),
                                         operation_logic='APPEND',
                                         pk=ProcessLineagePK(
                                             process_ref=ProcessRef(by_guid=self.process.to_guid()),
                                             data_flow=dataflow))._report()
                if lineage.to_guid() not in self.sent_runs:
                    from_schema_ref = set(x.from_schema_ref.by_guid for x in lineage.pk.data_flow)
                    to_schema_ref =  set(x.to_schema_ref.by_guid for x in lineage.pk.data_flow)
                    self.lineage_and_ds[lineage.to_guid()] = {'from_schema_ref':list(from_schema_ref),
                                                              'to_schema_ref':to_schema_ref}


                    lineage_run = LineageRun(
                        pk=LineageRunPK(lineage_ref=ProcessLineageRef(by_guid=lineage.to_guid()),
                                        process_run_ref=ProcessRunRef(by_guid=self.process_run.to_guid()),
                                        timestamp=round(self.timestamp)))._report()
                    self.sent_runs.append(lineage.to_guid())


                    def create_stats(schema_guid):
                        stats_df = self.real_schema_df[schema_guid]
                        stats = self.extract_stats(stats_df)
                        if stats is None and isinstance(stats_df, KensuDatasourceAndSchema):
                            # in this special case, the stats are reported not by kensu-py,
                            # but by some external library called from .f_publish_stats callback
                            # as an example - stats publishing directly from Apache Spark JVM
                            # for pyspark's python-JVM interop jobs (where data moves between Spark & Python)
                            stats_df.f_publish_stats(lineage_run.to_guid())
                        elif stats is not None:
                            self.schema_stats[schema_guid] = stats
                            if lineage_run.to_guid() not in self.stats_to_send:
                                self.stats_to_send[lineage_run.to_guid()] = {}
                            self.stats_to_send[lineage_run.to_guid()][schema_guid] = stats
                            if schema_guid == to_guid:
                                if 'nrows' in stats and self.compute_delta:
                                    # fixme: extract a helper
                                    output_nrows = stats['nrows']
                                    #TODO Corner case: if from_pk = to_pk
                                    for input_schema_guid in from_pks:
                                        input_stats = self.schema_stats.get(input_schema_guid)
                                        input_nrows = input_stats and input_stats.get('nrows')
                                        if input_nrows:
                                            delta_nrows = input_nrows - output_nrows
                                            input_name = self.logical_name_by_guid.get(input_schema_guid, self.schema_name_by_guid.get(input_schema_guid))
                                            clean_input_name = self.name_for_stats(input_name)
                                            stats['delta.nrows_' + clean_input_name + '.abs']=delta_nrows
                                            stats['delta.nrows_' + clean_input_name + '.decrease in %'] = round(100*delta_nrows/input_nrows,2)
                                    self.schema_stats[schema_guid] = stats
                                    self.stats_to_send[lineage_run.to_guid()][schema_guid] = stats


                        #FIXME should be using extractors instead
                        if is_ml_model:
                            model_name = self.model[to_guid][1]
                            metrics = self.model[to_guid][2]
                            import json
                            hyperparams = json.dumps(self.model[to_guid][3])

                            model = Model(ModelPK(name=model_name))._report()
                            train = ModelTraining(pk=ModelTrainingPK(model_ref=ModelRef(by_guid=model.to_guid()),
                                                                     process_lineage_ref=ProcessLineageRef(
                                                                         by_guid=lineage.to_guid())))._report()
                            r=ModelMetrics(pk=ModelMetricsPK(model_training_ref=ModelTrainingRef(by_guid=train.to_guid()),
                                                           lineage_run_ref=LineageRunRef(by_guid=lineage_run.to_guid()),
                                                           stored_in_schema_ref=SchemaRef(by_guid=to_guid)),
                                         metrics=metrics, hyper_params_as_json=hyperparams)._report()
                    for schema in from_pks:
                        if self.input_stats:
                            create_stats(schema)
                    create_stats(to_guid)


                    for check in self.check_rules:
                        if list(check.keys())[0] == 'nrows_consistency':
                            create_kensu_nrows_consistency(check[list(check.keys())[0]])
                    self.send_rules()

                    lineage_run_id = lineage_run.to_guid()
                    for lineage_run_id in self.stats_to_send:
                        for schema_id in self.stats_to_send[lineage_run_id]:
                            self.send_stats(lineage_run_id,schema_id,self.stats_to_send[lineage_run_id][schema_id])
                    if lineage_run_id in self.stats_to_send:
                        del self.stats_to_send[lineage_run_id]

                    self.check_local_rules()

    def create_dependencies(self,destination_guid, guid, origin_column, column, all_deps,
                            dependencies_per_columns_rt):
        visited = list()
        visited.append((guid,column))
        self.dependencies_per_columns = dependencies_per_columns_rt
        filtered_dependencies = all_deps[all_deps['GUID'] == guid]

        filtered_dependencies = filtered_dependencies[filtered_dependencies['COLUMNS'] == str(column)]
        if destination_guid in self.dependencies_per_columns:
            for row in filtered_dependencies.iterrows():
                row = row[1]

                if row['FROM_ID'] in self.real_schema_df:
                    if origin_column in self.dependencies_per_columns[destination_guid]:
                        if row['FROM_ID'] in self.dependencies_per_columns[destination_guid][origin_column]:
                            self.dependencies_per_columns[destination_guid][origin_column][row['FROM_ID']] = \
                            self.dependencies_per_columns[destination_guid][origin_column][row['FROM_ID']] + \
                            row['FROM_COLUMNS']
                        else:
                            self.dependencies_per_columns[destination_guid][origin_column][row['FROM_ID']] = row[
                                'FROM_COLUMNS']
                    else:
                        self.dependencies_per_columns[destination_guid][origin_column] = {}
                        self.dependencies_per_columns[destination_guid][origin_column][row['FROM_ID']] = row[
                            'FROM_COLUMNS']
                        # dependencies_per_columns[guid][row['FROM_ID']] = row['FROM_COLUMNS']
                else:
                    guid = row['FROM_ID']
                    columns = row['FROM_COLUMNS']
                    for column in columns:
                        if (guid,column) not in visited:
                            self.create_dependencies(destination_guid, guid, origin_column, column, all_deps,
                                                self.dependencies_per_columns)
        else:
            self.dependencies_per_columns[destination_guid] = {}
            self.create_dependencies(destination_guid, guid, origin_column, column, all_deps,
                                self.dependencies_per_columns)

    def get_dependencies(self):
        return self.dependencies
    def add_dependency(self, i, o, mapping_strategy=mapping_strategies.FULL):
        if not isinstance(i, tuple):
            (ids, isc) = self.extractors.extract_data_source_and_schema(i, self.default_physical_location_ref)
            i = (i, ids, isc)

        if not isinstance(o, tuple):
            (ods, osc) = self.extractors.extract_data_source_and_schema(o, self.default_physical_location_ref)
            o = (o, ods, osc)

        self.dependencies.append((i, o, mapping_strategy))
    def add_dependencies(self, ins, outs, mapping_strategy=mapping_strategies.FULL):
        new_ins = []
        for i in ins:
            if not isinstance(i, tuple):
                (ids, isc) = self.extractors.extract_data_source_and_schema(i, self.default_physical_location_ref)
                i = (i, ids, isc)
                new_ins.append(i)

        new_outs = []
        for o in outs:
            if not isinstance(o, tuple):
                (ods, osc) = self.extractors.extract_data_source_and_schema(o, self.default_physical_location_ref)
                o = (o, ods, osc)
                new_outs.append(o)

        self.dependencies.append((new_ins, new_outs, mapping_strategy))

    def get_lineage_name(self,
                         data_flow  # type: list[SchemaLineageDependencyDef]
                         ):
        inputs = ",".join(sorted(self.to_schema_names([d.from_schema_ref.by_guid for d in data_flow])))
        outputs = ",".join(sorted(self.to_schema_names([d.to_schema_ref.by_guid for d in data_flow])))
        return "Lineage to {} from {}".format(outputs, inputs)


    @property
    def s(self):
        return self.start_lineage(True)


    def start_lineage(self, report_stats=True):
        lineage_builder = LineageBuilder(self, report_stats)
        return lineage_builder


    def new_lineage(self, process_lineage_dependencies, report_stats=True, **kwargs):
        # if the new_lineage has a model training in it (output),
        #   then kwargs will be pass to the function to compute metrics
        #     ex: kwargs["y_test"] can refer to the test set to compute CV metrics
        data_flow = [d.toSchemaLineageDependencyDef() for d in process_lineage_dependencies]
        lineage = ProcessLineage(name=self.get_lineage_name(data_flow),
                                 operation_logic="APPEND",
                                 # FIXME? => add control and the function level like report_stats
                                 pk=ProcessLineagePK(
                                     process_ref=self.process.to_ref(),
                                     data_flow=data_flow
                                 )
                                 )._report()

        if self.timestamp is None:
            self.timestamp=int(time.time()) * 1000

        lineage_run = LineageRun(pk=LineageRunPK(
            lineage_ref=lineage.to_ref(),
            process_run_ref=self.process_run.to_ref(),
            timestamp=self.timestamp
        )
        )._report()

        data_flow_inputs = list(
            {to_hash_key(d.input_schema): (d.input_schema, d.input) for d in process_lineage_dependencies}.values())
        data_flow_outputs = list(
            {to_hash_key(d.output_schema): (d.output_schema, d.output) for d in process_lineage_dependencies}.values())

        for (schema, df) in (data_flow_inputs + data_flow_outputs):
            stats = self.extractors.extract_stats(df)
            if report_stats and stats is not None:
                DataStats(pk=DataStatsPK(schema_ref=schema.to_ref(),
                                         lineage_run_ref=lineage_run.to_ref()),
                          stats=stats,
                          extra_as_json=None)._report()

        # TODO Machine Learning part for OUTPUTS ONLY (right ?)
        for (schema, df) in data_flow_outputs:
            ml = self.extractors.extract_machine_learning_info(df)
            if ml is not None:
                model = Model(ModelPK(ml["name"]))._report()
                model_training = ModelTraining(ModelTrainingPK(model_ref=model.to_ref(),
                                                               process_lineage_ref=lineage.to_ref())
                                               )._report()

                metrics = self.extractors.extract_machine_learning_metrics(df, **kwargs)
                if len(metrics) > 0:
                    hp = self.extractors.extract_machine_learning_hyper_parameters(df)
                    ModelMetrics(pk=ModelMetricsPK(
                        model_training_ref=model_training.to_ref(),
                        lineage_run_ref=lineage_run.to_ref(),
                        stored_in_schema_ref=schema.to_ref()
                    ),
                        metrics=metrics,
                        hyper_params_as_json=json.dumps(hp)
                    )._report()

    def send_stats(self,lineage_run_id, schema_id,stats):

        if stats is not None:
            DataStats(pk=DataStatsPK(schema_ref=SchemaRef(by_guid=schema_id),
                                     lineage_run_ref=LineageRunRef(by_guid=lineage_run_id)),
                      stats=stats,
                      extra_as_json=None)._report()

    def send_rules(self):
        if self.rules and self.api_url:
            process_id = self.process.to_guid()
            project_id = self.process_run.projects_refs[0].by_guid
            env_name = self.process_run.environment
            cv = self.process_run.executed_code_version_ref.by_guid

            for map in self.rules:
                for lds_id in map:
                    field_name = map[lds_id]['field']
                    fun = map[lds_id]['fun']
                    context = map[lds_id]['context']

                    token_content = jwt.decode(self.kensu_api.api_client.default_headers["X-Auth-Token"], options={"verify_signature": False})
                    if 'SANDBOX_USER_HASH' in token_content:
                        sandbox_prefix = token_content['SANDBOX_USER_HASH'] + "-"
                        project_id = sandbox_prefix + project_id
                        process_id = sandbox_prefix + process_id
                        cv = sandbox_prefix +cv
                    else:
                        sandbox_prefix = ''

                    data = self.sdk.get_lineages_in_project(project_id, process_id, env_name, cv)

                    try:
                        lds_guid = [e['datasource'] for e in data['data']['nodes'] if e['datasource']['name'] == lds_id][0][
                            'id']
                    except:
                        try:
                            lds_guid = sandbox_prefix+"logical-data-source-" + lds_id
                        except:
                            logging.info("LDS Guid %s not in this lineage"%lds_id)
                            lds_guid = None

                    if lds_guid is not None:
                        if context == "DATA_STATS":
                            lineage_ids = set(
                                [data['data']['links'][i]['lineage']['id'] for i in range(len(data['data']['links']))])
                            for lineage_id in lineage_ids:
                                current_rules = self.sdk.get_rules_for_ds_in_project(lds_guid, lineage_id, project_id,
                                                                                     env_name)
                                current_range_rules = {i['fieldName']: i['uuid'] for i in
                                                       current_rules['data']['predicates'] if
                                                       i['functionName'] == 'Range' and (i['environment'] == env_name)}
                                current_frequency_rule = [i['uuid'] for i in current_rules['data']['predicates'] if
                                                          i['functionName'] == 'Frequency' and (
                                                                      i['environment'] == env_name)]
                                if fun['name'] == 'Range' and (field_name in current_range_rules):
                                    self.sdk.update_rule(current_range_rules[field_name], fun)
                                elif fun['name'] == 'Frequency' and current_frequency_rule:
                                    self.sdk.update_rule(current_frequency_rule[0], fun)

                                else:
                                    self.sdk.create_rule(lds_guid, lineage_id, project_id, process_id, env_name, field_name,
                                                         fun)

                        elif context == "LOGICAL_DATA_SOURCE":
                            current_rules = self.sdk.get_all_rules_for_ds(lds_guid)
                            current_range_rules = {i['fieldName']: i['uuid'] for i in
                                                   current_rules['data']['predicates'] if
                                                   i['functionName'] == 'Range'}
                            current_variation_rules = {i['fieldName']: i['uuid'] for i in
                                                   current_rules['data']['predicates'] if
                                                   i['functionName'] == 'Variability'}
                            if fun['name'] == 'Range' and (field_name in current_range_rules):
                                self.sdk.update_rule(current_range_rules[field_name], fun)
                            elif fun['name'] == 'Variability' and (field_name in current_variation_rules):
                                self.sdk.update_rule(current_variation_rules[field_name], fun)

                            else:
                                self.sdk.create_rule(lds_id=lds_guid, field_name=field_name,
                                                     fun=fun,context = "LOGICAL_DATA_SOURCE")




    def check_local_rules(self):
        from kensu.utils.exceptions import NrowsConsistencyError
        for check in self.check_rules:
            if 'check_nrows_consistency' in check:
                for datasource in check['check_nrows_consistency']:
                    for rule in check['check_nrows_consistency'][datasource]:
                        for field in rule:
                            if rule[field]['output_nrows'] != rule[field]['input_nrows'] :
                                e = NrowsConsistencyError(datasource, rule[field]['input_nrows'],
                                                                rule[field]['output_nrows'])
                                if self.raise_on_check_failure:
                                    raise e
                                else:
                                    logging.warning(e)



