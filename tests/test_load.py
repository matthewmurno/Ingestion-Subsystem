import pandas as pd
import psycopg2
import pytest

from src.load import load


class FakeCursor:
    def __init__(self, fail_on_sql_substring: str | None = None):
        self.executed = []
        self.closed = False
        self.fail_on_sql_substring = fail_on_sql_substring

    def execute(self, sql, params=None):
        if self.fail_on_sql_substring and self.fail_on_sql_substring in sql:
            raise psycopg2.Error("Simulated DB error")
        self.executed.append((sql, params))

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


class FakeConn:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def _make_loaded_data(people_df: pd.DataFrame, rejects_df: pd.DataFrame | None = None, stg_admissions_df: pd.DataFrame | None = None,
):
    hospitals_df = pd.DataFrame(
        [{"hospital_id": 1, "hospital_name": "General Hospital"}]
    )

    doctors_df = pd.DataFrame(
        [{"doctor_id": 10, "doctor_name": "Dr. Who", "hospital_id": 1}]
    )

    conditions_df = pd.DataFrame(
        [{"condition_id": 100, "condition_name": "Flu"}]
    )

    insurance_df = pd.DataFrame(
        [{"insurance_id": 200, "provider_name": "Health Inc"}]
    )

    test_results_df = pd.DataFrame(
        [{"test_result_id": 300, "result_label": "normal"}]
    )

    admission_types_df = pd.DataFrame(
        [{"admission_type_id": 400, "type_name": "Emergency"}]
    )

    admissions_df = pd.DataFrame(
        [
            {
                "admission_id": 500,
                "person_id": people_df.iloc[0]["person_id"],
                "doctor_id": 10,
                "condition_id": 100,
                "insurance_id": 200,
                "admission_type_id": 400,
                "test_result_id": 300,
                "date_of_admission": pd.Timestamp("2024-01-01"),
                "discharge_date": pd.Timestamp("2024-01-02"),
                "billing_amount": 1234.56,
                "room_number": 101,
                "medication": "Tylenol",
            }
        ]
    )

    if stg_admissions_df is None:
        stg_admissions_df = pd.DataFrame(
            [
                {
                    "name": "John Doe",
                    "age": 30,
                    "gender": "M",
                    "blood_type": "A+",
                    "medical_condition": "Flu",
                    "date_of_admission": pd.Timestamp("2024-01-01"),
                    "doctor": "Dr. Who",
                    "hospital": "General Hospital",
                    "insurance_provider": "Health Inc",
                    "billing_amount": 1234.56,
                    "room_number": 101,
                    "admission_type": "Emergency",
                    "discharge_date": pd.Timestamp("2024-01-02"),
                    "medication": "Tylenol",
                    "test_results": "normal",
                }
            ]
        )

    if rejects_df is None:
        rejects_df = pd.DataFrame(
            [
                {
                    "name": "Bad Row",
                    "age": "unknown",
                    "gender": "X",
                    "blood_type": "O+",
                    "medical_condition": "Unknown",
                    "date_of_admission": pd.NA,
                    "doctor": "No One",
                    "hospital": "Nowhere",
                    "insurance_provider": "None",
                    "billing_amount": pd.NA,
                    "room_number": pd.NA,
                    "admission_type": "Unknown",
                    "discharge_date": pd.NA,
                    "medication": "",
                    "test_results": "N/A",
                    "missing_columns": "age, billing_amount",
                }
            ]
        )

    return {
        "people": people_df,
        "hospitals": hospitals_df,
        "doctors": doctors_df,
        "conditions": conditions_df,
        "insurance": insurance_df,
        "test_results": test_results_df,
        "admission_types": admission_types_df,
        "stg_admissions": stg_admissions_df,
        "admissions": admissions_df,
        "rejects": rejects_df,
    }


def test_load_happy_path_inserts_and_commits(monkeypatch):
    people_df = pd.DataFrame(
        [
            {
                "person_id": 1,
                "name": "John Doe",
                "age": 30,
                "gender": "M",
                "blood_type": "A+",
            }
        ]
    )

    loaded_data = _make_loaded_data(people_df)
    fake_cursor = FakeCursor()
    fake_conn = FakeConn(fake_cursor)

    def fake_connect(dsn):

        assert dsn == "postgresql://test-db"
        return fake_conn

    monkeypatch.setattr("src.load.psycopg2.connect", fake_connect)

    load(loaded_data, "postgresql://test-db")

    assert any('CREATE TABLE IF NOT EXISTS "dim_people"' in sql for sql, _ in fake_cursor.executed)
    assert any("TRUNCATE stg_rejects" in sql for sql, _ in fake_cursor.executed)
    assert any("INSERT INTO dim_people" in sql for sql, _ in fake_cursor.executed)
    assert any("INSERT INTO fact_admission_data" in sql for sql, _ in fake_cursor.executed)
    assert any("INSERT INTO stg_rejects" in sql for sql, _ in fake_cursor.executed)

    assert fake_conn.commits >= 3
    assert fake_conn.rollbacks == 0
    assert fake_cursor.closed
    assert fake_conn.closed


def test_load_people_age_handling(monkeypatch):
    people_df = pd.DataFrame(
        [
            {
                "person_id": 1,
                "name": "Young",
                "age": 25,
                "gender": "M",
                "blood_type": "O+",
            },
            {
                "person_id": 2,
                "name": "Unknown Age",
                "age": pd.NA,
                "gender": "F",
                "blood_type": "A-",
            },
            {
                "person_id": 3,
                "name": "Too Old",
                "age": 150,
                "gender": "F",
                "blood_type": "B+",
            },
        ]
    )

    loaded_data = _make_loaded_data(people_df)
    fake_cursor = FakeCursor()
    fake_conn = FakeConn(fake_cursor)

    def fake_connect(dsn):
        return fake_conn

    monkeypatch.setattr("src.load.psycopg2.connect", fake_connect)

    load(loaded_data, "postgresql://test-db")

    people_inserts = [
        params for sql, params in fake_cursor.executed if "INSERT INTO dim_people" in sql
    ]
    assert len(people_inserts) == 3

    ages = [p[2] for p in people_inserts]

    assert ages[0] == 25
    assert ages[1] is None
    assert ages[2] == 150 


def test_load_rolls_back_on_db_error(monkeypatch):
    people_df = pd.DataFrame(
        [
            {
                "person_id": 1,
                "name": "Error Person",
                "age": 40,
                "gender": "M",
                "blood_type": "AB+",
            }
        ]
    )

    loaded_data = _make_loaded_data(people_df)
    fake_cursor = FakeCursor(fail_on_sql_substring="INSERT INTO dim_people")
    fake_conn = FakeConn(fake_cursor)

    def fake_connect(dsn):
        return fake_conn

    monkeypatch.setattr("src.load.psycopg2.connect", fake_connect)

    load(loaded_data, "postgresql://test-db")

    assert fake_conn.rollbacks == 1
    assert fake_cursor.closed
    assert fake_conn.closed
