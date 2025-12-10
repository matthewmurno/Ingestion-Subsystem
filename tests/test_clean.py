import pandas as pd
from src.clean import clean

def test_clean_normalizes_column_names_and_strings():
    raw = pd.DataFrame({
        " Name ": [" john doe ", "  jane SMITH"],
        "GENDER": ["m", " f "],
        "hospitAL": ["   general hospital", "city CLINIC  "],
    })

    result = clean(raw)
    assert list(result.columns) == ["name", "gender", "hospital"]

    assert result.loc[0, "name"] == "John Doe"
    assert result.loc[1, "name"] == "Jane Smith"

    assert result["gender"].tolist() == ["M", "F"]

    assert result.loc[0, "hospital"] == "General Hospital"
    assert result.loc[1, "hospital"] == "City Clinic"

def test_clean_handles_missing_optional_columns_gracefully():
    raw = pd.DataFrame({
        "NAME": ["john"],
        "GENDER": ["m"],
    })

    result = clean(raw)

    assert "name" in result.columns
    assert "gender" in result.columns

def test_clean_applies_numeric_rules_and_rounding():
    raw = pd.DataFrame(
        {
            "name": ["Valid Age", "Too Old"],
            "age": [30, 150],
            "billing_amount": [123.456, 10],
            "room_number": ["101", "5"],
        }
    )

    result = clean(raw)

    assert pd.api.types.is_numeric_dtype(result["age"])
    assert result.loc[0, "age"] == 30
    assert pd.isna(result.loc[1, "age"])

    assert pd.api.types.is_numeric_dtype(result["billing_amount"])
    assert result.loc[0, "billing_amount"] == 123.46
    assert result.loc[1, "billing_amount"] == 10.00

    assert pd.api.types.is_numeric_dtype(result["room_number"])
    assert result.loc[0, "room_number"] == 101
    assert result.loc[1, "room_number"] == 5

def test_clean_enforces_allowed_values_for_test_results_and_medication_case():
    raw = pd.DataFrame(
        {
            "name": ["Alice", "Bob"],
            "medication": ["ibUProfeN", "ASPIRIN"],
            "test_results": ["abnormal", "UNKNOWN"],
        }
    )

    result = clean(raw)

    assert result.loc[0, "medication"] == "Ibuprofen"
    assert result.loc[1, "medication"] == "Aspirin"

    assert result.loc[0, "test_results"] == "abnormal"

    assert pd.isna(result.loc[1, "test_results"])