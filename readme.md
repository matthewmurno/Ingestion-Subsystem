
# Data Ingestion Subsystem
A config-driven ETL pipeline built in Python that ingests raw tabular data (e.g. healthcare admission CSVs), cleans and normalizes it, splits it into dimension and fact tables, and loads it into a PostgreSQL database with referential integrity and test coverage.

## Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Running the Pipeline](#running-the-pipeline)
- [Testing](#testing)
- [Logging](#logging)
- [Extending the Pipeline](#extending-the-pipeline)
- [Future Improvements](#future-improvements)
- [License](#license)

## Overview
This project is a reusable ingestion subsystem designed to demonstrate a realistic ETL workflow:

1. **Read** raw data from configurable sources (currently file-based: CSV / JSON).
2. **Clean** and normalize column names and values.
3. **Transform** the cleaned data into a set of dimension and fact tables using configuration-driven schemas.
4. **Load** those tables into PostgreSQL, enforcing constraints and foreign keys.
5. **Handle rejects** for invalid rows instead of silently dropping them.

It is built with maintainability and testability in mind, using YAML configuration, structured logging, and pytest-based test coverage.

## Features
- **Config-driven sources & schemas**
  - Sources and table schemas are defined in YAML (no hard-coded paths or schemas).
- **Data cleaning layer**
  - Normalizes column names (e.g. `Name` → `name`, `Hospital Name` → `hospital_name`).
  - Trims whitespace, standardizes casing, and handles optional columns gracefully.
- **Transform to dimensions + facts**
  - Splits a single raw dataset into multiple dimension tables (e.g. people, doctors, hospitals, conditions, insurance, test_results, admission_types) plus a fact table (admissions) and a rejects table.
  - Enforces “not null” requirements based on config and routes invalid rows to `rejects`.
- **Schema-aware table creation**
  - Builds `CREATE TABLE` statements from YAML schema definitions, including:
    - Column types
    - Nullability and uniqueness
    - Primary keys
    - Foreign key relations between tables
- **Upsert-style loading**
  - Uses `INSERT ... ON CONFLICT DO UPDATE` (or equivalent pattern) to support idempotent loads and incremental updates.
- **Robust logging**
  - Structured logs for each phase (read, clean, transform, load) for easy debugging.
- **Automated tests & coverage**
  - Pytest test suite for core modules.
  - Coverage configuration via `.coveragerc`.


## Architecture

At a high level:
```text
Raw Source (CSV/JSON)
        |
        v
     src.read
   (read_csv/read_json)
        |
        v
     src.clean
   (normalize columns/values)
        |
        v
   src.transform
(split into dimensions/facts,
 assign primary keys, build rejects)
        |
        v
      src.load
(ensure tables exist, apply schema,
  upsert into Postgres, persist rejects)
```
Configuration (YAML) sits alongside this flow and is used to drive:
Which sources to read
Column mappings
Not-null constraints
Table schemas (types, PKs, FKs, etc.)
## Project Structure
```text
Project Structure
Ingestion-Subsystem/
├─ config/
│  └─ sources.yml        # YAML config for sources, connection details, and schemas
├─ logs/
│  └─ *.log              # Log files written by the pipeline (gitignored)
├─ src/
│  ├─ __init__.py        # (optional) package marker
│  ├─ read.py            # Reading CSV/JSON based on source config
│  ├─ clean.py           # Normalization & cleaning of raw data
│  ├─ transform.py       # Build dimension & fact DataFrames + rejects
│  ├─ load.py            # Table creation & upsert logic into PostgreSQL
│  ├─ config.py          # YAML config loader & helper accessors
│  ├─ logger.py          # Shared logger factory
│  └─ main.py            # Orchestration entrypoint for end-to-end ETL
├─ tests/
│  ├─ test_read.py       # Tests for reading functions
│  ├─ test_clean.py      # Tests for cleaning logic
│  ├─ test_transform.py  # Tests for dimension/fact building
│  └─ test_load.py       # Tests for table creation + load behavior
├─ .coveragerc           # Coverage configuration
└─ .gitignore
```
Note: Some filenames may differ slightly; see the src/ directory for the definitive list.
## Getting Started
### Prerequisites
Python 3.10+ (3.11 recommended)
PostgreSQL instance you can connect to
(Optional) A virtual environment tool (venv, virtualenv, conda, etc.)

You’ll also need the following Python packages (installed manually or via your own requirements.txt):
pandas
psycopg2-binary
PyYAML
pytest
pytest-cov

### Installation
Clone the repository:
```text
git clone https://github.com/matthewmurno/Ingestion-Subsystem.git
cd Ingestion-Subsystem
```
Create and activate a virtual environment (recommended):
```text
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
```
Install dependencies:
```text
pip install pandas psycopg2-binary PyYAML pytest pytest-cov
(Or adapt to your own dependency management setup.)
```
## Configuration
All configuration lives under config/sources.yml.

At a high level, the file includes:

Defaults (e.g. db_url for PostgreSQL)
Source definitions (type, path, options)

A simplified example:
```text
defaults:
  db_url: postgresql://user:password@localhost:5432/etl_db

sources:
  - name: healthcare_csv
    type: csv
    path: data/healthcare_dataset_dirty.csv
    table: raw_healthcare

tables:
  people:
    columns:
      person_id:
        type: UUID
        primary_key: true
      name:
        type: TEXT
        nullable: false
      age:
        type: INTEGER
        nullable: false
      gender:
        type: TEXT
        nullable: false
      blood_type:
        type: TEXT
        nullable: false
    not_null_source_columns:
      - name
      - age
      - gender
      - blood_type

  # ... other tables: doctors, hospitals, conditions, insurance, etc.
```
Key helpers (from src/config.py) include:
```text
load_config() – load the YAML file.

get_source_config(name) – fetch config for a particular source.

get_table_schema(table_name) – schema for a table.

get_source_not_null_columns(table_name) – required columns from the source.

get_source_to_db_mapping(table_name) – mapping from source column names to DB column names.

get_pk_column_and_type(table_name) – primary key settings.

Update db_url, file paths, and schemas to match your environment and data.
```

## Running the Pipeline
From the repository root:

# Run the full ETL using the default config
```text
python -m src.main
```
**Common flow inside src.main (simplified):**

Load configuration from config/sources.yml.

1. Read the configured source (e.g. healthcare CSV).

2. Clean the DataFrame.

3. Transform into multiple DataFrames (dimensions, facts, rejects).

4. Connect to PostgreSQL using db_url from config.

5. Ensure all tables exist using the configured schemas.

6. Upsert the data into the appropriate tables.

You can customize main.py (or add CLI arguments) to:

1. Pick a different source,
2. Use a different config file path,
3. Run only specific pipeline stages for debugging.

## Testing
Run the test suite from the project root:
```text
pytest
```
To see coverage (configured via .coveragerc):

```text
pytest --cov=src --cov-report=term-missing
```
The coverage configuration typically:
Targets the src/ package.

Excludes tests/ and any generated files/logs.

Helps keep coverage around or above your desired threshold.

## Logging
The project uses a shared logger factory defined in src/logger.py:
```text
from src.logger import get_logger
logger = get_logger(__name__)
```
Logs are written both to the console and to files under logs/ (depending on your logger configuration). Typical messages 
include:

Start/end of each ETL phase.

Shapes of DataFrames at key points.

Warnings for dropped or rejected rows.

Errors with stack traces (via logger.exception).

This makes it easier to debug the pipeline and understand what happened during a run.

## Extending the Pipeline
Some ideas for extending this project:

Additional data sources

Add new type handlers in src/read.py (e.g. APIs, databases, S3).

More validation rules

Extend transform.py to validate ranges, enumerations, or cross-field rules.

Route violations to the rejects table with descriptive reasons.

More tables / schemas

Add new table definitions in config/sources.yml.

Update the transformation logic to populate them.

Custom CLI

Use argparse or typer to expose config path, dry-run options, or step filters.

## Future Improvements

Planned or possible improvements:

Containerization with Docker for consistent local/dev setups.

Integration with a scheduler/orchestrator (e.g. Airflow, Prefect) for repeatable runs.

Metrics collection (row counts, reject rates) pushed to a dashboard.

Automatic schema migrations or drift detection based on the YAML config.