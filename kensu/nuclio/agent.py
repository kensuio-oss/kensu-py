import atexit
import json
import logging
import os
from datetime import datetime, timedelta
import functools
import random
from json import JSONDecodeError
from typing import Set, Optional, Dict
from dataclasses import dataclass

from kensu.utils.helpers import to_datasource

from kensu.client import DataStats, DataStatsPK, DataSourcePK, DataSource, SchemaPK, Schema, PhysicalLocationRef, \
    DataSourceRef, FieldDef, LineageRun, LineageRunPK, ProcessLineage, ProcessLineagePK, ProcessRef, \
    SchemaLineageDependencyDef, SchemaRef, ProcessRun, Process, ProcessRunRef, ProcessLineageRef, LineageRunRef, \
    ProcessPK, ProcessRunPK
from kensu.utils.kensu import Kensu

from nuclio_sdk.context import Context
from nuclio_sdk.event import Event

#from kensu.utils import KensuProvider

# Status:
# - shutdown hook - implemented, not tested
# - estimation +/- done, define kafka DS broker + topic + consumer_group? no partition?
# - define which metrics to compute


FREQ = timedelta(seconds=int(os.environ.get('KSU_NUCLIO_REPORTING_INTERVAL_SECONDS') or 60))

# FIXME: move init kensu inside decorator?
from kensu.utils.kensu_provider import KensuProvider


def init_kensu_py(process_name, logical_data_source_naming_strategy):
    KensuProvider().initKensu(
        process_name=process_name,
        pandas_support=False,
        numpy_support=False,
        allow_reinit=True,
        logical_data_source_naming_strategy=logical_data_source_naming_strategy
    )


class GenericAggregator:
    id: str

    def plus(self, other: 'GenericAggregator') -> 'GenericAggregator':
        pass

    def to_metrics(self) -> Dict[str, float]:
        pass


@dataclass
class NullCounterAggregator(GenericAggregator):
    nullrows: float
    field_name: str

    @property
    def id(self) -> str:
        return f"{self.field_name}.null"

    @staticmethod
    def create(field_name: str, value: Optional[object]):
        return NullCounterAggregator(nullrows=1 if (value is None) else 0,
                                     field_name=field_name)

    def plus(self, other: 'NullCounterAggregator') -> 'GenericAggregator':
        return NullCounterAggregator(
            nullrows=self.nullrows + other.nullrows,
            field_name=self.field_name
        )

    def to_metrics(self) -> Dict[str, float]:
        return {
            f"{self.field_name}.nullrows": self.nullrows,
        }


@dataclass
class MinMaxAggregator(GenericAggregator):
    min: float
    max: float
    field_name: str

    @property
    def id(self) -> str:
        return f"{self.field_name}.min_max"

    @staticmethod
    def create(field_name: str, value: float):
        return MinMaxAggregator(min=value, max=value, field_name=field_name)

    def plus(self, other: 'MinMaxAggregator') -> 'GenericAggregator':
        return MinMaxAggregator(
            min=self.min if (self.min < other.min) else other.min,
            max=self.max if (self.max > other.max) else other.max,
            field_name=self.field_name
        )

    def to_metrics(self) -> Dict[str, float]:
        return {
            f"{self.field_name}.min": self.min,
            f"{self.field_name}.max": self.max,
        }


@dataclass
class MetricsAccumulator:
    nrows: int
    # FIXME: MIN,MAX OFFSET
    # nullrows? of root keys?
    # .min/.max of numeric
    aggregators_by_id: Dict[str, GenericAggregator]

    schema: Dict[str, str]  # field_name -> datatype

    @staticmethod
    def zero():
        return MetricsAccumulator(
            nrows=0,
            schema=dict(),
            aggregators_by_id={}
        )

    @staticmethod
    def one_event(schema: Optional[dict], values: Optional[dict]):
        return MetricsAccumulator(
            nrows=1,
            schema=schema or dict(),
            aggregators_by_id=dict([
                (aggr.id, aggr)
                for name, value in (values or {}).items()
                for aggr in (
                    ([
                        # MinMax only makes sense for numeric values
                        MinMaxAggregator.create(field_name=name, value=value),
                     ] if (isinstance(value, float) or isinstance(value, int)) else []
                     ) + [
                        # FIXME: redo how null-counter works, if value not present, it should still consider it NULL
                        # so we need NonNullCounter and then compute difference between nrows
                        NullCounterAggregator.create(field_name=name, value=value),
                    ])
            ])
        )

    def is_empty(self):
        return self.nrows == 0

    def add(self, other: 'MetricsAccumulator'):
        # mutable!
        # do not override not NoneType with NoneType ?
        # but FIXME it would still report NoneType if not present within the interval
        # alternatively, excluding NoneTypes from schema would never report these
        self.schema.update(other.schema)
        self.nrows += other.nrows
        all_aggr_keys = set(self.aggregators_by_id.keys()).union(set(other.aggregators_by_id.keys()))
        new_aggregators = {}
        for aggr_key in all_aggr_keys:
            a1 = self.aggregators_by_id.get(aggr_key)
            a2 = other.aggregators_by_id.get(aggr_key)
            if a1 and a2:
                new_aggregators[aggr_key] = a1.plus(a2)
            else:
                new_aggregators[aggr_key] = a1 or a2
        self.aggregators_by_id = new_aggregators

    def add_event(self, event, event_schema: Dict[str, str], values: Optional[dict]):
        self.add(MetricsAccumulator.one_event(schema=event_schema, values=values))
        return self

    def get_combined_schema_dict(self):
        # field name -> datatype
        return self.schema or {'unknown': 'Unknown'}

    def get_metrics_dict(self) -> Dict[str, float]:
        metrics = {
            'nrows': self.nrows,
        }
        for agg in self.aggregators_by_id.values():
            metrics.update(agg.to_metrics())
        return metrics


@dataclass
class KafkaDatasource:
    brokers: str
    topic: str
    # FIXME: a single Kafka topic quite often (e.g in event ingestion) has multiple different schemas
    #  based on some `event_type` discriminator field, do we need to group by that?
    # event_type: str

    metrics: MetricsAccumulator


    consumer_group: Optional[str] = None
    # FIXME: offset is per consumer_group & partition, might be interesting to track minInputOffset, maxInputOffset !


    @property
    def sorted_brokers(self):
        return ','.join(sorted(self.brokers.split(',')))

    @property
    def location(self):
        # FIXME: brokers and consumer group not avail; but we have kafka name
        return f"kafka://{self.sorted_brokers}/topic={self.topic}"

    def report_to_kensu(self):
        k = KensuProvider().instance()
        physical_location_ref = PhysicalLocationRef(by_guid=k.UNKNOWN_PHYSICAL_LOCATION.to_guid())

        ds_pk = DataSourcePK(location=self.location, physical_location_ref=physical_location_ref)
        logical_naming = k.logical_naming
        ds = to_datasource(ds_pk=ds_pk,
                              format='kafka',
                              location=self.location,
                              logical_data_source_naming_strategy=logical_naming,
                              name=self.location)._report()

        schema_pk = SchemaPK(data_source_ref=DataSourceRef(by_pk=ds_pk),
                             fields=[FieldDef(name=field_name, field_type=field_dt, nullable=True)
                                     for field_name, field_dt in self.metrics.get_combined_schema_dict().items()])
        schema = Schema(name=f"Schema :: {self.location}", pk=schema_pk)

        ds._report()
        schema._report()
        return ds, schema

    def report_datastats(self, schema_ref: SchemaRef, lineage_run_ref: LineageRunRef):
        return DataStats(pk=DataStatsPK(schema_ref=schema_ref,
                                        lineage_run_ref=lineage_run_ref),
                         stats=self.metrics.get_metrics_dict())._report()


    @staticmethod
    def from_topic(topic: str, cluster_name: Optional[str]):
        return KafkaDatasource(
            # FIXME: no consumer group in event?
            # FIXME: no broker url in event?
            brokers=cluster_name or 'unknown-kafka-cluster',
            topic=topic,
            metrics=MetricsAccumulator.zero()
        )

    @staticmethod
    def from_event(event: Event):
        topic = event.topic
        event_timestamp = event.timestamp  # FIXME: use this somehow
        offset = event.offset
        if topic and offset:
            return KafkaDatasource.from_topic(topic=topic, cluster_name=event.trigger.name)
        return None


def extract_datatype(v):
    return type(v).__name__


def extract_value(v):
    return v


def extract_event_fields(event_body,
                         value_extractor_fn,
                         try_parse_str_as_json: bool = True,
                         ):
    schema_items = {}
    if isinstance(event_body, dict):
        # FIXME: or do we want deep schema?
        for k, v in event_body.items():
            schema_items[k] = value_extractor_fn(v)
    elif isinstance(event_body, str):
        # FIXME: try to parse str as JSON
        if try_parse_str_as_json:
            try:
                import json
                # FIXME: add prefix
                schema_items.update(
                    dict([("event_body." + k, v)
                          for k, v in extract_event_fields(
                            event_body=json.loads(event_body),
                            value_extractor_fn=value_extractor_fn,
                            try_parse_str_as_json=False).items()
                          ]))
            except JSONDecodeError:
                logging.info(f"Unable to parse string as JSON")
        schema_items['event_body'] = value_extractor_fn(event_body)
    elif isinstance(event_body, bytes):
        try:
            decoded_str = event_body.decode("utf-8")
            return extract_event_fields(event_body=decoded_str,
                                        value_extractor_fn=value_extractor_fn,
                                        try_parse_str_as_json=True)
        except UnicodeDecodeError as e:
            logging.info(f"Unable to decode body as unicode: {e}")
    return schema_items



@dataclass
class KensuOutputLineageInfo:
    # FIXME: generalize these, to more DS types
    output: KafkaDatasource
    inputs: Dict[str, KafkaDatasource]  # location -> DS

    @staticmethod
    def extract_values_for_metrics(input_event: Event, event_body):
        # add schema and metrics for reporting in future
        stream_processing_metrics = {
            # FIXME: these might be always 0. nuclio bug?
            # https://stackoverflow.com/questions/78126285/why-is-the-event-offset-always-0-for-my-kafka-triggered-nuclio-function
            f"nuclio_stream.shard{input_event.shard_id}.offset": input_event.offset,
            f"nuclio_stream.num_shards": input_event.num_shards,
        }
        decoded_data = extract_event_fields(
            event_body=event_body,
            value_extractor_fn=extract_value)
        return dict(decoded_data, **stream_processing_metrics)

    @staticmethod
    def extract_schema(event_body):
        schema_fields = extract_event_fields(event_body=event_body, value_extractor_fn=extract_datatype)
        # exclude NoneType's from schema
        return dict([(k, v)
                     for (k, v) in schema_fields.items()
                     if v and v != 'NoneType'])

    def add_input_event(self, event: Event):
        # extract kafka info input from event
        input_ds_tmp = KafkaDatasource.from_event(event)
        if not input_ds_tmp:
            return None
        input_location = input_ds_tmp.location
        # find existing input or add a new one
        input = self.inputs.get(input_location)
        if not input:
            input = input_ds_tmp
            self.inputs[input_location] = input

        input.metrics.add_event(
            event=event,
            event_schema=self.extract_schema(event_body=event.body),
            values=self.extract_values_for_metrics(input_event=event, event_body=event.body)
        )
        return self

    def add_output_info(self,
                        input_event: Event,
                        output_data,
                        explicit_schema: Optional[Dict[str, str]]):
        self.output.metrics.add(MetricsAccumulator.one_event(
            schema=explicit_schema or self.extract_schema(event_body=output_data),
            values=self.extract_values_for_metrics(input_event=input_event, event_body=output_data)
        ))


    def report_to_kensu(self, process: Process, process_run: ProcessRun):
        # FIXME: report unknown output if none was reported explicitly; maybe same for unknown input(s)?
        out_ds, out_schema = self.output.report_to_kensu()
        input_schemas_by_input_path = {}
        for input in self.inputs.values():
            input_ds, input_schema = input.report_to_kensu()
            input_schemas_by_input_path[input.location] = input_schema  # FIXME: should these be properties of KafkaDatasource ?

        k = KensuProvider().instance()
        # FIXME: use custom process or from k.process?
        process_guid = process.to_guid() # k.process.to_guid()
        output_schema_ref = SchemaRef(by_guid=out_schema.to_guid())
        # lineage
        data_flow = [SchemaLineageDependencyDef(from_schema_ref=SchemaRef(by_guid=i_schema.to_guid()),
                                                to_schema_ref=output_schema_ref,
                                                # FIXME: or should we report column_data_dependencies=None ?
                                                column_data_dependencies={'unknown': ['unknown']})
                     for i_schema in input_schemas_by_input_path.values()]
        lineage = ProcessLineage(name=f'Lineage to {str(self.output.location)} from {list(self.inputs.keys())}',
                                 operation_logic='APPEND',
                                 pk=ProcessLineagePK(process_ref=ProcessRef(
                                     by_guid=process_guid),
                                     data_flow=data_flow))._report()
        timestamp_now = int(round(datetime.now().timestamp()*1000))
        lineage_run = LineageRun(pk=LineageRunPK(process_run_ref=ProcessRunRef(by_guid=process_run.to_guid()),
                                 lineage_ref=ProcessLineageRef(by_guid=lineage.to_guid()),
                                                 # FIXME: shall we use max event timestamp instead?
                                 timestamp=timestamp_now))._report()
        lineage_run_ref = LineageRunRef(by_guid=lineage_run.to_guid())

        # output metrics
        self.output.report_datastats(schema_ref=output_schema_ref, lineage_run_ref=lineage_run_ref)
        # input metrics
        for input_path, input_schema in input_schemas_by_input_path.items():
            input = self.inputs.get(input_path)
            if not input:
                continue
            input.report_datastats(schema_ref=SchemaRef(by_guid=input_schema.to_guid()),
                                   lineage_run_ref=lineage_run_ref)





@dataclass
class KensuLineage:
    lineage_by_output: Dict[str, KensuOutputLineageInfo]
    process_name: str

    def add_output_lineage(self,
                           input_event: Event,
                           output_ds: KafkaDatasource,
                           output_schema: Optional[Dict[str, str]],
                           output_data: Optional[object]):
        if not output_schema:
            output_schema = {}
        input_location = output_ds.location
        # find existing lineage or add a new one
        existing_output = self.lineage_by_output.get(input_location)
        if not existing_output:
            existing_output = KensuOutputLineageInfo(
                output=output_ds,
                inputs={}
            )
            self.lineage_by_output[input_location] = existing_output

        existing_output.add_input_event(input_event)
        existing_output.add_output_info(input_event=input_event,
                                        output_data=output_data,
                                        explicit_schema=output_schema)

    def report_to_kensu(self):
        k: Kensu = KensuProvider().instance()
        # process_name = self.process_name
        # process = Process(pk=ProcessPK(qualified_name=process_name))._report()
        # process_run = ProcessRun(pk=ProcessRunPK(process_ref=ProcessRef(by_pk=process.pk),
        #                                          qualified_name=process_name),
        #                          launched_by_user_ref=None,
        #                          executed_code_version_ref=None,
        #                          environment=None,
        #                          projects_refs=None
        #                          )._report()
        # FIXME: do I need new process run for each reporting? probably yes. if so reinit Kensu?
        # if it's a long running Nuclio job, and we don't reinit or resend process/process-run etc,
        # performing delete by token would not allow to continue ingesting without restarting the Nuclio stream/jobs
        # thus need to call k.report_process_info() each time
        k.report_process_info()
        # init_kensu_py(k.process.pk.qualified_name)
        for ds_loc, output_info in self.lineage_by_output.items():
            output_info.report_to_kensu(process=k.process, process_run=k.process_run)

    @staticmethod
    def empty(process_name: str):
        return KensuLineage(lineage_by_output={},
                            process_name=process_name)


def report_on_shutdown(context):
    print("Reporting Kensu events on Python process exit...")
    send_report_if_exists(context=context, dt=datetime.now())
    print("Done reporting Kensu events on Python process exit.")


def send_report_if_exists(context: Context, dt: datetime):
    # FIXME: timing of this looks fishy
    lineage = context.user_data.accumulated_info
    if lineage:
        send_report(
            context,
            context.user_data.last_report_time,
            lineage,
        )
        context.user_data.accumulated_info = KensuLineage.empty(lineage.process_name)

    context.user_data.last_report_time = dt  # Reset report time FIXME: should this be start or end time of func()?


def track_kensu(process_name=None, logical_data_source_naming_strategy=None):
    """
    :param process_name: if None, will use package::handler_func_name as default
    :return:
    """
    def actual_decorator(handler_func):
        # FIXME: add try catch
        # FIXME: if that's in current file, it has no package
        qualname_handler = handler_func.__qualname__
        fn_filename = handler_func.__code__.co_filename

        nonlocal process_name  # Indicate that process_name is non-local
        if not process_name:
            process_name = f"Nuclio :: {fn_filename} :: {qualname_handler}()"
        # FIXME: is this called multiple times?

        @functools.wraps(handler_func)
        def wrapper_timed_report(context, event):
            now: datetime = datetime.now()
            # P.S. `.current_event` and `.accumulated_info` must be set before running the `handler_func()`
            # otherwise reporting wouldn't work the way it is implemented now
            context.user_data.current_event = event
            if not hasattr(context.user_data, "last_report_time"):
                init_kensu_py(process_name, logical_data_source_naming_strategy)
                # if this is the first invocation of the handler
                context.user_data.last_report_time = now
                context.user_data.accumulated_info = KensuLineage.empty(process_name=process_name)
                # report fn needs to have context, so register a python shutdown hook on first invocation
                atexit.register(report_on_shutdown, context)

            # Run the regular handler function logic
            result = handler_func(context, event)

            context.user_data.current_event = None
            # Check if the reporting period has passed
            if now - context.user_data.last_report_time >= FREQ:
                send_report_if_exists(context=context, dt=now)

            return result

        return wrapper_timed_report
    return actual_decorator


def send_report(context: Context, last_report_time, data: KensuLineage):
    context.logger.info(f"Reporting data[{last_report_time}]: {data}")
    data.report_to_kensu()


KAFKA = 'kafka'


def add_target(context, tpe, info):
    if tpe == KAFKA:
        kensu_add_kafka_output(context, info)


# {"field": "type"}
def kensu_add_kafka_output(context, topic, cluster_name=None, output_data=None, schema=None):
    if hasattr(context.user_data, "accumulated_info") and hasattr(context.user_data, "current_event"):
        accumulated_info = context.user_data.accumulated_info
        input_event = context.user_data.current_event
        accumulated_info.add_output_lineage(
            input_event=input_event,
            output_ds=KafkaDatasource.from_topic(topic=topic,
                                                 cluster_name=cluster_name),
            output_schema=schema,  # FIXME: extract output schema & values from event_body
            output_data=output_data  # FIXME: extract output values from event_body
        )
