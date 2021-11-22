# kensu-py
Open source some py integration modules to automate Data and Analytics Observability

[![Join the chat at https://gitter.im/kensuio-oss/kensu-py](https://badges.gitter.im/kensuio-oss/kensu-py.svg)](https://gitter.im/kensuio-oss/kensu-py?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)
[![Live the full adventure and try a Data and Analytics Observability platform](https://img.shields.io/static/v1?label=Platform&message=Try%20Kensu&color=blue)](https://hubs.li/H0M3Jrd0)

## Data Observability Features

Adds Data Observability capabilities such as `lineage` tracking, `data profiling` of input and output data sources, `data set` and `schema` discovery for python libraries:

- pandas
- numpy
- scikit-learn
- google bigquery
- boto3
- requests
- pysftp
- gluonts
- psycopg2 (PostgreSQL)

## Installation

### From pypi

`pip install kensu`

## Development

### Build

`pip install ".[all]"`

### Run tests

```
pip install ".[all]"
CONF_FILE=tests/unit/conf.ini pytest
```

## Usage

### Configuration file

The default configuration file is located at the root folder `conf.ini`.
Otherwise, the `CONF_FILE` environment variable can point to another one.

### Configuration keys

#### General
Connect to API
- api_url
- api_token

Meta information about the python application
- project_names
- environment
- process_name
- user_name
- code_location

Behavior of the data observability features
- do_report: if False, no data observability information are reporterd
- logical_naming: **TODO** - explain data source grouping strategies such as File, ...
- mapping: **TODO**

Extra libraries support (TODO: to be extracted in different modules)
- pandas_support: Boolean
- sklearn_support: Boolean
- bigquery_support: Boolean
- tensorflow_support: Boolean
- sql_util_url: URL to an external server capable of handling SQL parsing into lineage

#### Reporters

- name: Name of the reporter (currently we use the class name as a convention, such as `KafkaReporter`, `PrintReporter`, `LoggingReporter`, `FileReporter`, `MultiReporter`)

Each reporter has its own conf keys.

##### name=MultiReporter

Dispatches to several reporters

- reporters: JSON array of the repoter names, e.g. reporters["KafkaReporter", "FileReporter"] 

##### name=KafkaReporter

- bootstrap_servers=[]
- topic=kensu-events

##### FileReporter

- file_name=kensu-events.jsonl

##### LoggingReporter

- level=WARN

## Data and Analytics Observability platform

Check out [Kensu](https://kensu.io) and the [trial program](https://hubs.li/H0M3Jrd0).
