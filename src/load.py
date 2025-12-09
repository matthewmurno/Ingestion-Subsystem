import pandas as pd
import psycopg2
from psycopg2.extensions import connection as PgConnection
from src.config import CONFIG, get_source_config

from src.logger import get_logger

logger = get_logger(__name__)

###Helper for Building '''CREATE IF NOT EXISTS''' Table Functions###
def build_create_table_sql(table_name, schema):
    columns_cfg = schema.get("columns", {})
    column_defs = []
    pk_cols = []
    fk_constraints = []

    for col_name, col_cfg in columns_cfg.items():
        col_type = col_cfg["type"]
        nullable = col_cfg.get("nullable", True)
        unique = col_cfg.get("unique", False)
        default = col_cfg.get("default")
        primary_key = col_cfg.get("primary_key", False)
        references = col_cfg.get("references")

        parts = [f'"{col_name}" {col_type}']

        if not nullable:
            parts.append("NOT NULL")
        if unique:
            parts.append("UNIQUE")
        if default is not None:
            parts.append(f"DEFAULT {default}")

        column_defs.append(" ".join(parts))

        if primary_key:
            pk_cols.append(f'"{col_name}"')

        if references:
            if isinstance(references, str):
                fk_constraints.append(
                    f'FOREIGN KEY ("{col_name}") REFERENCES {references}'
                )
            else:
                ref_table = references["table"]
                ref_column = references.get("column", "id")
                on_delete = references.get("on_delete")
                on_update = references.get("on_update")

                clause = (
                    f'FOREIGN KEY ("{col_name}") '
                    f'REFERENCES "{ref_table}" ("{ref_column}")'
                )

                if on_delete:
                    clause += f" ON DELETE {on_delete}"
                if on_update:
                    clause += f" ON UPDATE {on_update}"

                fk_constraints.append(clause)

    all_defs = list(column_defs)
    if pk_cols:
        all_defs.append(f"PRIMARY KEY ({', '.join(pk_cols)})")

    all_defs.extend(fk_constraints)

    columns_sql = ",\n  ".join(all_defs)
    return f'CREATE TABLE IF NOT EXISTS "{table_name}" (\n  {columns_sql}\n);'

###Checking If Tables Exist, Else Run build_create_table_sql(table_name, schema) to Create Them###
def ensure_all_tables_exist(conn):
    schemas = CONFIG.get("schemas", {})
    if not schemas:
        logger.warning("No schemas found in CONFIG['schemas']; skipping table creation.")
        return

    with conn.cursor() as cur:
        for table_name, schema in schemas.items():
            create_sql = build_create_table_sql(table_name, schema)
            logger.debug("Ensuring table %s exists", table_name)
            cur.execute(create_sql)
    conn.commit()

###Logic for Insertion Vs Upsertion, Functionality for Both Cases###
def build_insert_or_upsert_sql(table_name: str, df: pd.DataFrame) -> tuple[str, list[str], list[str]]:
    schemas_cfg = CONFIG.get("schemas", {})
    if table_name not in schemas_cfg:
        raise KeyError(f"No schema found for table {table_name!r}")

    table_schema = schemas_cfg[table_name]
    columns_cfg = table_schema.get("columns", {})

    schema_cols = list(columns_cfg.keys())
    df_cols = set(df.columns)

    insert_columns = [c for c in schema_cols if c in df_cols]
    if not insert_columns:
        raise ValueError(f"No overlapping columns between df and schema for table {table_name!r}")

    pk_cols = [name for name, cfg in columns_cfg.items() if cfg.get("primary_key")]
    conflict_cols = [c for c in pk_cols if c in insert_columns]

    col_list_sql = ", ".join(insert_columns)
    placeholders = ", ".join(["%s"] * len(insert_columns))

    if not conflict_cols:
        sql = f"INSERT INTO {table_name} ({col_list_sql}) VALUES ({placeholders});"
        return sql, insert_columns, []

    non_pk_insert_cols = [c for c in insert_columns if c not in conflict_cols]
    conflict_cols_sql = ", ".join(conflict_cols)

    if non_pk_insert_cols:
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in non_pk_insert_cols)
        sql = (
            f"INSERT INTO {table_name} ({col_list_sql}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_cols_sql}) DO UPDATE SET {set_clause};"
        )
    else:
        sql = (
            f"INSERT INTO {table_name} ({col_list_sql}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_cols_sql}) DO NOTHING;"
        )

    return sql, insert_columns, conflict_cols

###Loading Logic W/ Edge Cases for Age Verification and Rejects Loading###
def insert_table(cur, table_name: str, df: pd.DataFrame) -> None:
    """
    Insert rows from df into the given table using schema-driven SQL.
    Handles special cases for people.age and rejects NA handling.
    """
    if df is None or df.empty:
        logger.info("DataFrame for table %s is empty; skipping insert.", table_name)
        return

    sql, insert_columns, conflict_cols = build_insert_or_upsert_sql(table_name, df)
    logger.debug(
        "Inserting into %s with columns %s (conflict on %s)",
        table_name,
        insert_columns,
        conflict_cols or "none",
    )

    for row in df[insert_columns].itertuples(index=False, name=None):
        values = []
        for col_name, value in zip(insert_columns, row):
            if table_name == "people" and col_name == "age":
                if pd.isna(value):
                    values.append(None)
                else:
                    try:
                        age_int = int(value)
                    except (TypeError, ValueError):
                        logger.warning(
                            "Non-numeric age %r for people; setting to NULL before insert",
                            value,
                        )
                        age_int = None
                    else:
                        if age_int < 0 or age_int > 120:
                            logger.warning(
                                "Invalid age %s for people; setting to NULL before insert",
                                age_int,
                            )
                            age_int = None
                    values.append(age_int)

            elif table_name == "rejects":
                if pd.isna(value):
                    values.append(None)
                else:
                    values.append(str(value))

            else:
                if pd.isna(value):
                    values.append(None)
                else:
                    values.append(value)

        cur.execute(sql, values)

def load(loaded_data, 
        db_url,
        mode: str = "full_refresh",
        batch_size: int | None = None
        ) -> None:
    ###Getting DF from Loaded_Data Dictionary###
    people_df = loaded_data["people"]
    hospitals_df = loaded_data["hospitals"]
    doctors_df = loaded_data["doctors"]
    conditions_df = loaded_data["conditions"]
    insurance_df = loaded_data["insurance"]
    test_results_df = loaded_data["test_results"]
    admission_types_df = loaded_data["admission_types"]
    admissions_df = loaded_data["admissions"]
    rejects_df = loaded_data["rejects"]

    logger.info("Starting load() with mode=%s, batch_size=%s", mode, batch_size or "all")

    logger.info("Starting load()")
    logger.info(
        "Row counts - people=%d, hospitals=%d, doctors=%d, conditions=%d, "
        "insurance=%d, test_results=%d, admission_types=%d, admissions=%d, rejects=%d",
        len(people_df),
        len(hospitals_df),
        len(doctors_df),
        len(conditions_df),
        len(insurance_df),
        len(test_results_df),
        len(admission_types_df),
        len(admissions_df),
        len(rejects_df),
    )

    try:
        ###Opening Connection###
        logger.info("Connecting to database...")
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        logger.info("Database connection established.")

        ###Running Table Creation and Committing###
        ensure_all_tables_exist(conn)

        conn.commit()

        logger.info("Tables created/verified successfully.")

        if mode == "full_refresh":
            ###Truncating Rejects Table for New Rejects###
            logger.info("Truncating tables and resetting identities...")
            cur.execute("""
                TRUNCATE rejects,
                        admission_data,
                        doctors,
                        hospitals,
                        conditions,
                        insurance,
                        admission_types,
                        test_results,
                        people
                RESTART IDENTITY;
            """)
            conn.commit()
            logger.info("Tables truncated.")

        elif mode == "incremental":
            logger.info(
                "Incremental mode: skipping TRUNCATE; "
                "upserts will apply on top of existing data."
            )
        else:
            raise ValueError(f"Unknown load mode: {mode!r}")


        ###Starting Table Insertion Logic###
        table_to_df = {
            "people": people_df,
            "hospitals": hospitals_df,
            "doctors": doctors_df,
            "conditions": conditions_df,
            "insurance": insurance_df,
            "test_results": test_results_df,
            "admission_types": admission_types_df,
            "admission_data": admissions_df,
            "rejects": rejects_df,
        }

        insertion_order = [
            "people",
            "hospitals",
            "doctors",
            "conditions",
            "insurance",
            "test_results",
            "admission_types",
            "admission_data",
            "rejects",
        ]

        logger.info("Starting schema-driven insert/upsert phase...")
        for table_name in insertion_order:
            df = table_to_df[table_name]

            if df is None or df.empty:
                logger.info("Table %s has no rows; skipping.", table_name)
                continue

            ###Checking If batch_size, If The Dataframe is Larger than Batchsize, Load Incrementally###
            if batch_size is not None and len(df) > batch_size:
                logger.info(
                    "Loading table %s in batches of %d rows (total %d rows)",
                    table_name,
                    batch_size,
                    len(df),
                )
                ###Adjusting the Pointer For the Position of DataFrame to Insert From###
                for start in range(0, len(df), batch_size):
                    end = start + batch_size
                    batch_df = df.iloc[start:end].copy()
                    insert_table(cur, table_name, batch_df)
                    conn.commit()
            else:
                insert_table(cur, table_name, df)
                conn.commit()

        logger.info("Load completed successfully.")

    except psycopg2.Error:
        logger.exception("Error in load() while working with the database.")
        if 'conn' in locals():
            conn.rollback()
            logger.info("Transaction rolled back due to error.")

    finally:
        if 'cur' in locals() and cur:
            cur.close()
        if 'conn' in locals() and conn:
            conn.close()
        logger.info("Database connection closed. End of load().")