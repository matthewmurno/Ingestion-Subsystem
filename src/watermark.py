from datetime import datetime

def ensure_state_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS etl_state (
            pipeline_name text PRIMARY KEY,
            last_admission_date timestamp
        )
    """)

def get_last_watermark(conn, pipeline_name="admissions"):
    with conn.cursor() as cur:
        ensure_state_table(cur)
        cur.execute(
            "SELECT last_admission_date FROM etl_state WHERE pipeline_name = %s",
            (pipeline_name,),
        )
        row = cur.fetchone()
    return row[0] if row else None

def update_watermark(conn, pipeline_name, new_value: datetime):
    with conn.cursor() as cur:
        ensure_state_table(cur)
        cur.execute(
            """
            INSERT INTO etl_state (pipeline_name, last_admission_date)
            VALUES (%s, %s)
            ON CONFLICT (pipeline_name)
            DO UPDATE SET last_admission_date = EXCLUDED.last_admission_date
            """,
            (pipeline_name, new_value),
        )
    conn.commit()