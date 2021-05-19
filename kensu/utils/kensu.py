import datetime
import getpass
import json
import logging
import os
import time

from kensu.client import *
from kensu.utils.simple_cache import *
from kensu.utils.dsl import mapping_strategies
from kensu.utils.dsl.extractors import Extractors
from kensu.utils.dsl.lineage_builder import LineageBuilder
from kensu.utils.helpers import to_hash_key
from kensu.utils.injection import Injection
from kensu.pandas import DataFrame,Series


class Kensu(object):
    # list of triples i, o, mapping strategy
    # i and o are either one or a list of triples (object, DS, SC)
    dependencies = []
    dependencies_mapping = []
    dependencies_per_columns = {}
    real_schema_df = {}
    sent_runs = []
    data_collectors = {}
    model={}


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
                logging.warn("kensu-py was unable to identify a git repo. The working dir is not a git repo?")
                pass
        except ImportError as e:
            logging.warn("Install GitPython for a maximum context about the GIT code repo if any")
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

    def __init__(self, api_url=None, auth_token=None, process_name=None,
                 user_name=None, code_location=None, init_context=True, do_report=True, report_to_file=False, offline_file_name=None, reporter=None, **kwargs):
        """
        """ 
        kensu_host = self.get_kensu_host(api_url)
        kensu_auth_token = auth_token

        self.cache = SimpleCache()

        self.extractors = Extractors()
        pandas_support = kwargs["pandas_support"] if "pandas_support" in kwargs else True
        sklearn_support = kwargs["sklearn_support"] if "sklearn_support" in kwargs else True
        bigquery_support = kwargs["bigquery_support"] if "bigquery_support" in kwargs else True
        tensorflow_support = kwargs["tensorflow_support"] if "tensorflow_support" in kwargs else True
        project_names = kwargs["project_names"] if "project_names" in kwargs else []
        environment = kwargs["environment"] if "environment" in kwargs else None
        timestamp = kwargs["timestamp"] if "timestamp" in kwargs else None
        logical_naming = kwargs["logical_naming"] if "logical_naming" in kwargs else None
        mapping = kwargs["mapping"] if "mapping" in kwargs else None
        report_in_mem = kwargs["report_in_mem"] if "report_in_mem" in kwargs else False



        self.extractors.add_default_supports(pandas_support=pandas_support, sklearn_support=sklearn_support,bigquery_support=bigquery_support,tensorflow_support=tensorflow_support)

        self.kensu_api = KensuEntitiesApi()
        self.kensu_api.api_client.host = kensu_host
        self.kensu_api.api_client.default_headers["X-Auth-Token"] = kensu_auth_token

        if timestamp is not None:
            self.kensu_api.api_client.default_headers["X-Entity-Creation-Time"] = timestamp
        else:
            timestamp = datetime.datetime.now().timestamp()*1000

        # add function to Kensu entities
        injection = Injection()
        injection.set_reporter(reporter)
        injection.set_do_report(do_report, offline_file_name=offline_file_name, report_to_file=report_to_file)
        injection.set_kensu_api(self.kensu_api)

        self.user = None
        self.code_base = None
        self.code_version = None
        self.timestamp = timestamp
        self.logical_naming = logical_naming
        self.mapping = mapping
        self.report_in_mem = report_in_mem

        self.set_default_physical_location(Kensu.UNKNOWN_PHYSICAL_LOCATION)
        # can be updated using set_default_physical_location
        self.init_context(process_name=process_name, user_name=user_name, code_location=code_location,
                          get_code_version=Kensu.discover_code_version, project_names=project_names, environment=environment, timestamp=timestamp)



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


    def init_context(self, process_name=None, user_name=None, code_location=None, get_code_version=None, project_names=None,environment=None,timestamp=None):

        if user_name is None:
            user_name = Kensu.discover_user_name()

        if code_location is None:
            code_location = Kensu.discover_code_location()

        self.user = User(pk=UserPK(user_name))._report()
        self.code_base = CodeBase(pk=CodeBasePK(code_location))._report()
        if get_code_version is None:
            get_code_version = Kensu.discover_code_version

        self.timestamp = timestamp
        if timestamp is not None:
            version = datetime.datetime.fromtimestamp(timestamp/1000).isoformat()
        else:
            version=get_code_version()
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

        #TODO timestamp for historical data

        process_run_name = process_name + "@" + datetime.datetime.now().isoformat()
        self.process_run = ProcessRun(
            pk=ProcessRunPK(process_ref=self.process.to_ref(), qualified_name=process_run_name)
            , launched_by_user_ref=self.user.to_ref()
            , executed_code_version_ref=self.code_version.to_ref()
            , projects_refs=self.project_refs
            , environment = environment
        )._report()
        


    def set_default_physical_location(self, pl):
        self.default_physical_location = pl
        pl._report()
        self.default_physical_location_ref = pl.to_ref()

    def get_dependencies(self):
        return self.dependencies

    def get_dependencies_mapping(self):
        return self.dependencies_mapping

    def add_dependencies_mapping(self, guid, col, from_guid, from_col, type):
        dep = {'GUID': guid,
               'COLUMNS': col,
               'FROM_ID': from_guid,
               'FROM_COLUMNS': from_col,
               'TYPE': type}
        self.dependencies_mapping.append(dep)

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

    def in_mem(self, var_name):
        return "in-memory-data://" + self.process.pk.qualified_name + "/" + var_name

    @property
    def s(self):
        return self.start_lineage(True)

    def start_lineage(self, report_stats=True):
        lineage_builder = LineageBuilder(self, report_stats)
        return lineage_builder

    # if the new_lineage has a model training in it (output),
    #   then kwargs will be pass to the function to compute metrics
    #     ex: kwargs["y_test"] can refer to the test set to compute CV metrics
    def new_lineage(self, process_lineage_dependencies, report_stats=True, **kwargs):
        data_flow = [d.toSchemaLineageDependencyDef() for d in process_lineage_dependencies]

        inputs = ",".join(sorted([d.from_schema_ref.by_guid for d in data_flow]))
        outputs = ",".join(sorted([d.to_schema_ref.by_guid for d in data_flow]))

        lineage = ProcessLineage(name=inputs+"->"+outputs,
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

    def report_with_mapping(self):
        import pandas as pd
        deps = self.dependencies_mapping
        ddf = pd.DataFrame(deps)
        df = ddf.set_index(['GUID', 'COLUMNS', 'FROM_ID']).groupby(['GUID', 'COLUMNS', 'FROM_ID']).agg(list)
        df = df[~df.index.duplicated(keep='first')].reset_index()

        unique_ids = list(df['GUID'].unique())

        if self.report_in_mem:
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

                lineage = ProcessLineage(name='Lineage', operation_logic='APPEND',
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


                lineage = ProcessLineage(name='Lineage to %s from %s' %(to_guid, (',').join(list(from_pks))), operation_logic='APPEND',
                                         pk=ProcessLineagePK(
                                             process_ref=ProcessRef(by_guid=self.process.to_guid()),
                                             data_flow=dataflow))._report()



                if lineage.to_guid() not in self.sent_runs:
                    lineage_run = LineageRun(
                        pk=LineageRunPK(lineage_ref=ProcessLineageRef(by_guid=lineage.to_guid()),
                                        process_run_ref=ProcessRunRef(by_guid=self.process_run.to_guid()),
                                        timestamp=round(self.timestamp)))._report()
                    self.sent_runs.append(lineage.to_guid())

                    for schema in schemas_pk:
                        stats_df = self.real_schema_df[schema]
                        try:
                            stats = self.extractors.extract_stats(stats_df)
                        except:
                            # FIXME weird... should be fine to delete (and try,except too)
                            if isinstance(stats_df, pd.DataFrame) or isinstance(stats_df, DataFrame) or isinstance(stats_df,Series) or isinstance(stats_df,pd.Series):
                                stats = self.extractors.extract_stats(stats_df)
                        if stats is not None:
                            DataStats(pk=DataStatsPK(schema_ref=SchemaRef(by_guid=schema),
                                                     lineage_run_ref=LineageRunRef(by_guid=lineage_run.to_guid())),
                                      stats=stats,
                                      extra_as_json=None)._report()
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



    dependencies_per_columns = {}
    def create_dependencies(self,destination_guid, guid, origin_column, column, all_deps,
                            dependencies_per_columns_rt):
        self.dependencies_per_columns = dependencies_per_columns_rt
        filtered_dependencies = all_deps[all_deps['GUID'] == guid]

        filtered_dependencies = filtered_dependencies[filtered_dependencies['COLUMNS'] == column]
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
                        self.create_dependencies(destination_guid, guid, origin_column, column, all_deps,
                                            self.dependencies_per_columns)
        else:
            self.dependencies_per_columns[destination_guid] = {}
            self.create_dependencies(destination_guid, guid, origin_column, column, all_deps,
                                self.dependencies_per_columns)