import pandas as pd
import uuid
from src.logger import get_logger
from src.config import (
    get_source_not_null_columns,
    get_pk_column_and_type,
    get_source_to_db_mapping,
    get_enum_values_from_check,
    get_table_columns,
)

logger = get_logger(__name__)

def build_dimension_df(
    source_df,
    table_name,
    extra_source_cols: list[str] | None = None,
    logger_label: str | None = None,
) -> pd.DataFrame:

    not_null_cols = get_source_not_null_columns(table_name)
    extra_source_cols = extra_source_cols or []

    all_cols = list(dict.fromkeys(not_null_cols + extra_source_cols))

    dim_df = (
        source_df[all_cols]
        .dropna(subset=not_null_cols)
        .drop_duplicates()
        .reset_index(drop=True)
    )

    mapping = get_source_to_db_mapping(table_name)
    dim_df = dim_df.rename(columns=mapping)

    pk_col, pk_type = get_pk_column_and_type(table_name)
    if pk_type.lower() == "uuid":
        dim_df[pk_col] = [str(uuid.uuid4()) for _ in range(len(dim_df))]
    else:
        dim_df[pk_col] = range(1, len(dim_df) + 1)

    label = logger_label or f"{table_name}_df"
    logger.info(
        "Built %s (no nulls): %d rows x %d columns",
        label,
        dim_df.shape[0],
        dim_df.shape[1],
    )

    return dim_df


def transform(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    logger.info(
        "Starting transform(): input df has %d rows x %d columns",
        df.shape[0],
        df.shape[1],
    )

    try:
        people_df = build_dimension_df(df, "people")
        hospitals_df = build_dimension_df(
            df,
            "hospitals",
            logger_label="hospitals_df (no nulls)",
        )

        doctors_df = build_dimension_df(
            df,
            "doctors",
            extra_source_cols=["hospital"],
            logger_label="doctors_df (pre-hospital merge, no nulls)",
        )

        hosp_pk_col, _ = get_pk_column_and_type("hospitals")

        doctors_df = doctors_df.merge(
            hospitals_df[["hospital_name", hosp_pk_col]],
            left_on="hospital", 
            right_on="hospital_name",
            how="left",
        )

        doctors_df = doctors_df.dropna(subset=[hosp_pk_col]).copy()
        doctors_df[hosp_pk_col] = doctors_df[hosp_pk_col].astype(int)

        if "hospital" in doctors_df.columns:
            doctors_df = doctors_df.drop(columns=["hospital"])

        conditions_df = build_dimension_df(df, "conditions")
        insurance_df = build_dimension_df(df, "insurance")
        test_results_df = build_dimension_df(df, "test_results")
        admission_types_df = build_dimension_df(df, "admission_types")

        logger.debug("Merging people into base df...")
        df = df.merge(
            people_df,
            on=["name", "age", "gender", "blood_type"],
            how="left",
        )

        logger.debug("Merging doctors into base df...")
        df = df.merge(
            doctors_df[["doctor_name", "hospital_name", "doctor_id"]],
            left_on=["doctor", "hospital"],
            right_on=["doctor_name", "hospital_name"],
            how="left",
        )

        logger.debug("Merging conditions into base df...")
        df = df.merge(
            conditions_df,
            left_on="medical_condition",
            right_on="condition_name",
            how="left",
        )

        logger.debug("Merging insurance into base df...")
        df = df.merge(
            insurance_df,
            left_on="insurance_provider",
            right_on="provider_name",
            how="left",
        )

        logger.debug("Merging test_results into base df...")
        df = df.merge(
            test_results_df,
            left_on="test_results",
            right_on="result_label",
            how="left",
        )

        logger.debug("Merging admission_types into base df...")
        df = df.merge(
            admission_types_df,
            left_on="admission_type",
            right_on="type_name",
            how="left",
        )

        logger.info(
            "Finished merges; df is now %d rows x %d columns",
            df.shape[0],
            df.shape[1],
        )

        admissions_required = df[
            [
                "person_id",
                "doctor_id",
                "condition_id",
                "insurance_id",
                "admission_type_id",
                "test_result_id",
                "date_of_admission",
                "discharge_date",
                "billing_amount",
                "room_number",
                "medication",
            ]
        ].copy()

        required_cols = [
            "person_id",
            "doctor_id",
            "condition_id",
            "insurance_id",
            "admission_type_id",
            "test_result_id",
            "date_of_admission",
            "discharge_date",
            "billing_amount",
            "room_number",
            "medication",
        ]

        missing_mask = admissions_required[required_cols].isna().any(axis=1)

        missing_columns_series = admissions_required[required_cols].isna().apply(
            lambda row: ",".join(row.index[row]), axis=1
        )

        rejects_df = df.loc[
            missing_mask,
            [
                "name",
                "age",
                "gender",
                "blood_type",
                "medical_condition",
                "date_of_admission",
                "doctor",
                "hospital",
                "insurance_provider",
                "billing_amount",
                "room_number",
                "admission_type",
                "discharge_date",
                "medication",
                "test_results",
            ],
        ].copy()

        rejects_df["missing_columns"] = missing_columns_series[missing_mask].values

        admissions_df = admissions_required[~missing_mask].reset_index(drop=True)
        admissions_df["admission_id"] = admissions_df.index + 1

        admissions_df = admissions_df[
            [
                "admission_id",
                "person_id",
                "doctor_id",
                "condition_id",
                "insurance_id",
                "admission_type_id",
                "test_result_id",
                "date_of_admission",
                "discharge_date",
                "billing_amount",
                "room_number",
                "medication",
            ]
        ]

        logger.info(
            "Built admissions_df: %d rows x %d columns",
            admissions_df.shape[0],
            admissions_df.shape[1],
        )

        logger.info(
            "After reject split: %d valid admissions, %d rejected rows",
            admissions_df.shape[0],
            rejects_df.shape[0],
        )

        result = {
            "people": people_df,
            "doctors": doctors_df,
            "hospitals": hospitals_df,
            "conditions": conditions_df,
            "insurance": insurance_df,
            "admission_types": admission_types_df,
            "test_results": test_results_df,
            "admissions": admissions_df,
            "rejects": rejects_df,
        }

        logger.info(
            "transform() completed successfully. Output tables: %s",
            {k: v.shape for k, v in result.items()},
        )

        return result

    except Exception:
        logger.exception("transform() failed.")
        raise
