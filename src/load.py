import pandas as pd
import psycopg2
from psycopg2.extensions import connection as PgConnection
from src.config import CONFIG, get_source_config

from src.logger import get_logger

logger = get_logger(__name__)

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

def load(loaded_data, db_url):
    people_df = loaded_data["people"]
    hospitals_df = loaded_data["hospitals"]
    doctors_df = loaded_data["doctors"]
    conditions_df = loaded_data["conditions"]
    insurance_df = loaded_data["insurance"]
    test_results_df = loaded_data["test_results"]
    admission_types_df = loaded_data["admission_types"]
    admissions_df = loaded_data["admissions"]
    rejects_df = loaded_data["rejects"]

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
        logger.info("Connecting to database...")
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        logger.info("Database connection established.")

        ensure_all_tables_exist(conn)


        conn.commit()
        logger.info("Tables created/verified successfully.")

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

        logger.info("Starting insertion.")
        logger.debug("Inserting into people...")
        for row in people_df.itertuples(index=False):
            try:
                age = row.age

                if pd.isna(age):
                    age = None
                else:
                    age = int(age)
                    if age < 0 or age > 120:
                        logger.warning(
                            "Invalid age %s for person %s; setting age to NULL before insert",
                            age,
                            row.name,
                        )
                        age = None

                person_id = row.person_id

                cur.execute(
                    """
                    INSERT INTO people (person_id, name, age, gender, blood_type)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (person_id) DO UPDATE
                    SET name = EXCLUDED.name,
                        age = EXCLUDED.age,
                        gender = EXCLUDED.gender,
                        blood_type = EXCLUDED.blood_type;
                    """,
                    (person_id, row.name, age, row.gender, row.blood_type),
                )

            except psycopg2.Error:
                logger.exception("Failed inserting people row: %s", row)
                raise

        logger.debug("Inserting into hospitals...")
        for row in hospitals_df.itertuples(index=False):
            cur.execute(
                """
                INSERT INTO hospitals (hospital_id, hospital_name)
                VALUES (%s, %s)
                ON CONFLICT (hospital_id) DO UPDATE
                SET hospital_name = EXCLUDED.hospital_name;
                """,
                (row.hospital_id, row.hospital_name)
            )

        logger.debug("Inserting into doctors...")
        for row in doctors_df.itertuples(index=False):
            cur.execute(
                """
                INSERT INTO doctors (doctor_id, doctor_name, hospital_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (doctor_id) DO UPDATE
                SET doctor_name = EXCLUDED.doctor_name,
                    hospital_id = EXCLUDED.hospital_id;
                """,
                (row.doctor_id, row.doctor_name, row.hospital_id)
            )

        logger.debug("Inserting into conditions...")
        for row in conditions_df.itertuples(index=False):
            cur.execute(
                """
                INSERT INTO conditions (condition_id, condition_name)
                VALUES (%s, %s)
                ON CONFLICT (condition_id) DO UPDATE
                SET condition_name = EXCLUDED.condition_name;
                """,
                (row.condition_id, row.condition_name)
            )

        logger.debug("Inserting into insurance...")
        for row in insurance_df.itertuples(index=False):
            cur.execute(
                """
                INSERT INTO insurance (insurance_id, provider_name)
                VALUES (%s, %s)
                ON CONFLICT (insurance_id) DO UPDATE
                SET provider_name = EXCLUDED.provider_name;
                """,
                (row.insurance_id, row.provider_name)
            )

        logger.debug("Inserting into test_results...")
        for row in test_results_df.itertuples(index=False):
            cur.execute(
                """
                INSERT INTO test_results (test_result_id, result_label)
                VALUES (%s, %s)
                ON CONFLICT (test_result_id) DO UPDATE
                SET result_label = EXCLUDED.result_label;
                """,
                (row.test_result_id, row.result_label)
            )

        logger.debug("Inserting into admission_types...")
        for row in admission_types_df.itertuples(index=False):
            cur.execute(
                """
                INSERT INTO admission_types (admission_type_id, type_name)
                VALUES (%s, %s)
                ON CONFLICT (admission_type_id) DO UPDATE
                SET type_name = EXCLUDED.type_name;
                """,
                (row.admission_type_id, row.type_name)
            )

        logger.debug("Inserting into admission_data...")
        for row in admissions_df.itertuples(index=False):
            cur.execute(
                """
                INSERT INTO admission_data (
                    admission_id,
                    person_id,
                    doctor_id,
                    condition_id,
                    insurance_id,
                    admission_type_id,
                    test_result_id,
                    date_of_admission,
                    discharge_date,
                    billing_amount,
                    room_number,
                    medication
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (admission_id) DO UPDATE
                SET person_id         = EXCLUDED.person_id,
                    doctor_id         = EXCLUDED.doctor_id,
                    condition_id      = EXCLUDED.condition_id,
                    insurance_id      = EXCLUDED.insurance_id,
                    admission_type_id = EXCLUDED.admission_type_id,
                    test_result_id    = EXCLUDED.test_result_id,
                    date_of_admission = EXCLUDED.date_of_admission,
                    discharge_date    = EXCLUDED.discharge_date,
                    billing_amount    = EXCLUDED.billing_amount,
                    room_number       = EXCLUDED.room_number,
                    medication        = EXCLUDED.medication;
                """,
                (
                    row.admission_id,
                    row.person_id,
                    row.doctor_id,
                    row.condition_id,
                    row.insurance_id,
                    row.admission_type_id,
                    row.test_result_id,
                    row.date_of_admission,
                    row.discharge_date,
                    row.billing_amount,
                    row.room_number,
                    row.medication,
                )
            )

        logger.debug("Inserting into rejects...")
        for row in rejects_df.itertuples(index=False):
            cur.execute(
                """
                INSERT INTO rejects (
                    name,
                    age,
                    gender,
                    blood_type,
                    medical_condition,
                    date_of_admission,
                    doctor,
                    hospital,
                    insurance_provider,
                    billing_amount,
                    room_number,
                    admission_type,
                    discharge_date,
                    medication,
                    test_results,
                    missing_columns
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    row.name,
                    None if pd.isna(row.age) else str(row.age),
                    row.gender,
                    row.blood_type,
                    row.medical_condition,
                    None if pd.isna(row.date_of_admission) else str(row.date_of_admission),
                    row.doctor,
                    row.hospital,
                    row.insurance_provider,
                    None if pd.isna(row.billing_amount) else str(row.billing_amount),
                    None if pd.isna(row.room_number) else str(row.room_number),
                    row.admission_type,
                    None if pd.isna(row.discharge_date) else str(row.discharge_date),
                    row.medication,
                    row.test_results,
                    row.missing_columns,
                ),
            )

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