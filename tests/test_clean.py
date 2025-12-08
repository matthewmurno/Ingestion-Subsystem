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