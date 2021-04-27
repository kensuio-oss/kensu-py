import logging
from hashlib import sha256

from kensu.client import UserPK, CodeBasePK, CodeVersionPK , PhysicalLocationPK , DataSourcePK , ProcessPK , SchemaPK , \
                                ProcessLineagePK , ProcessRunPK , LineageRunPK , DataStatsPK , ModelPK , ModelTrainingPK , \
                                ModelMetricsPK  , ProcessRunStatsPK , ProjectPK



class KensuClassHandlers(object):

    @classmethod
    def guid_pk(cls, pk):
        sPK = cls.serializePK(pk)
        hashed = sha256(sPK.encode("utf-8")).hexdigest()
        return "k-" + hashed

    @classmethod
    def guid(cls, o):
        return cls.guid_pk(o.pk)

    # Case switcher to create main map of fields => see `serializePK` function
    @classmethod
    def caseUserPK(cls, o):
        return {
            "_dam_entity_type": "USER"
            , "name": o.name
        }

    @classmethod
    def caseCodeBasePK(cls, o):
        return {
            "_dam_entity_type": "CODE_BASE"
            , "location": o.location
        }

    @classmethod
    def caseCodeVersionPK(cls, o):
        return {
            "_dam_entity_type": "CODE_VERSION"
            , "version": o.version
            , "codebaseRef": cls.serializeRef(o.codebase_ref)
        }

    @classmethod
    def casePhysicalLocationPK(cls, o):
        return {
            "_dam_entity_type": "PHYSICAL_LOCATION"
            , "city": o.city.lower()
            , "country": o.country.lower()
        }

    @classmethod
    def caseDataSourcePK(cls, o):
        return {
            "_dam_entity_type": "DATA_SOURCE"
            , "location": o.location
            , "physical-location": cls.serializeRef(o.physical_location_ref)
        }

    @classmethod
    def caseProcessPK(cls, o):
        return {
            "_dam_entity_type": "PROCESS"
            , "qualifiedName": o.qualified_name
        }

    @classmethod
    def caseSchemaPK(cls, o):
        return {
            "_dam_entity_type": "SCHEMA"
            , "dataSourceRef": cls.serializeRef(o.data_source_ref)
            , "fields": cls.serializeFields(o.fields)
        }

    @classmethod
    def caseProcessLineagePK(cls, o):
        return {
            "_dam_entity_type": "PROCESS_LINEAGE"
            , "processRef": cls.serializeRef(o.process_ref)
            , "dataFlow": cls.serializeDataFlow(o.data_flow)
        }

    @classmethod
    def caseProcessRunPK(cls, o):
        return {
            "_dam_entity_type": "PROCESS_RUN"
            , "processRef": cls.serializeRef(o.process_ref)
            , "qualifiedName": o.qualified_name
        }

    @classmethod
    def caseLineageRunPK(cls, o):
        return {
            "_dam_entity_type": "LINEAGE_RUN"
            , "lineageRef": cls.serializeRef(o.lineage_ref)
            , "processRunRef": cls.serializeRef(o.process_run_ref)
            , "timestamp": o.timestamp
        }

    @classmethod
    def caseDataStatsPK(cls, o):
        return {
            "_dam_entity_type": "DATA_STATS"
            , "schemaRef": cls.serializeRef(o.schema_ref)
            , "lineageRunRef": cls.serializeRef(o.lineage_run_ref)
        }

    @classmethod
    def caseModelPK(cls, o):
        return {
            "_dam_entity_type": "MODEL"
            , "name": o.name
        }

    @classmethod
    def caseModelTrainingPK(cls, o):
        return {
            "_dam_entity_type": "MODEL_TRAINING"
            , "modelRef": cls.serializeRef(o.model_ref)
            , "processLineageRef": cls.serializeRef(o.process_lineage_ref)
        }

    @classmethod
    def caseModelMetricsPK(cls, o):
        return {
            "_dam_entity_type": "MODEL_METRICS"
            , "modelTrainingRef": cls.serializeRef(o.model_training_ref)
            , "lineageRunRef": cls.serializeRef(o.lineage_run_ref)
            , "storedInSchemaRef": cls.serializeRef(o.stored_in_schema_ref)
        }

    @classmethod
    def caseModelMonitorPK(cls, o):
        return {
            "_dam_entity_type": "MODEL_MONITOR"
            , "monitoredSchemaRef": cls.serializeRef(o.monitored_schema_ref)
            , "timestamp": o.timestamp
        }

    @classmethod
    def caseProcessRunStatsPK(cls, o):
        return {
            "_dam_entity_type": "PROCESS_RUN_STATS"
            , "processRunRef": cls.serializeRef(o.process_run_ref)
            , "timestamp": o.timestamp
        }

    @classmethod
    def caseProjectPK(cls, o):
        return {
            "_dam_entity_type": "PROJECT"
            , "name": o.name
        }

    @classmethod
    def caseSchemaFieldTagPK(cls, o):
        return {
            "_dam_entity_type": "SCHEMA_FIELD_TAG"
            , "schemaRef": cls.serializeRef(o.schema_ref)
            , "fieldName": o.field_name
            , "tagID": o.tag_id
        }

    CaseSwitcher = {
        UserPK: caseUserPK,
        CodeBasePK: caseCodeBasePK,
        CodeVersionPK: caseCodeVersionPK,
        PhysicalLocationPK: casePhysicalLocationPK,
        DataSourcePK: caseDataSourcePK,
        ProcessPK: caseProcessPK,
        SchemaPK: caseSchemaPK,
        ProcessLineagePK: caseProcessLineagePK,
        ProcessRunPK: caseProcessRunPK,
        LineageRunPK: caseLineageRunPK,
        DataStatsPK: caseDataStatsPK,
        ModelPK: caseModelPK,
        ModelTrainingPK: caseModelTrainingPK,
        ModelMetricsPK: caseModelMetricsPK,
        ProcessRunStatsPK: caseProcessRunStatsPK,
        ProjectPK: caseProjectPK,
    }

    @classmethod
    def serializePK(cls, o):
        clazz = o.__class__
        attrs = clazz.swagger_types

        keys = cls.CaseSwitcher[clazz].__func__(KensuClassHandlers, o)

        if (len(keys) != len(attrs) + 1):  # +1 because we add `_kensu_entity_type`
            logging.error(
                "Error serialization keys, it looks like there are different counts " + 
                "of serialized keys than fields in the pk of clazz=" +
                str(clazz) +
                ", attrs=", str(attrs) +
                ", keys=", str(keys)
            )

        serializedKeys = [str.format("{} -> {}", k, v) for [k, v] in keys.items()]
        serializedKeys.sort()
        serializedPK = "\n".join(serializedKeys)
        return serializedPK

    @classmethod
    def serializeRef(cls, ref):
        if ref.by_guid is not None:
            return ref.by_guid
        else:
            return cls.guid_pk(ref.by_pk)

    @classmethod
    def serializeFields(cls, fields):
        fieldsAsStrings = [
            "FieldDef(name: {}, fieldType: {}, nullable: {})".format(f.name, f.field_type, str(f.nullable).lower()) for
            f in fields]
        fieldsAsStrings.sort()
        serializedFields = "[" + ",".join(fieldsAsStrings) + "]"
        return serializedFields

    @classmethod
    def serializeDataFlow(cls, defs):
        def handleDef(d):
            fr = cls.serializeRef(d.from_schema_ref)
            to = cls.serializeRef(d.to_schema_ref)
            cdd = cls.serializeDependencies(d.column_data_dependencies)
            ccd = cls.serializeDependencies(d.column_control_dependencies)
            return "SchemaLineageDependencyDef(from: {}, to: {}, dataDeps: {}, controlDeps: {})".format(fr, to, cdd,
                                                                                                        ccd)

        defsAsStrings = [handleDef(d) for d in defs]
        defsAsStrings.sort()
        serializedDataFlow = "[" + ",".join(defsAsStrings) + "]"
        return serializedDataFlow

    @classmethod
    def serializeDependencies(cls, deps):
        if deps is None or len(deps) == 0:
            return "{}"
        else:
            depsAsStrings = ["{} -> [{}]".format(outputField, ",".join(sorted(inputFields))) for
                             [outputField, inputFields] in deps.items()]
            depsAsStrings.sort()

            serializedDeps = "{" + ",".join(depsAsStrings) + "}"
            return serializedDeps
