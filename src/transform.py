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

###Helper to Build Tables Based On schema.yml's Not Null Columns, Generating PK based on PK Column###
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

###Merging on PK Column based on schema.yaml Columns###
def merge_dimension(
    df,
    dim_df,
    table_name,
    left_on: list[str] | None = None,
    right_on: list[str] | None = None,
    extra_right_cols: list[str] | None = None,
) -> pd.DataFrame:
    mapping = get_source_to_db_mapping(table_name)

    if left_on is None or right_on is None:
        left_on = list(mapping.keys())
        right_on = [mapping[src] for src in left_on]

    pk_col, _ = get_pk_column_and_type(table_name)

    extra_right_cols = extra_right_cols or []

    cols_to_keep = list(dict.fromkeys(right_on + [pk_col] + extra_right_cols))

    logger.debug(
        "Merging %s into base df on left=%s right=%s; keeping columns=%s",
        table_name,
        left_on,
        right_on,
        cols_to_keep,
    )

    return df.merge(
        dim_df[cols_to_keep],
        left_on=left_on,
        right_on=right_on,
        how="left",
    )

###Building Dimension Tables for Admission and Rejects, Merging in Columns from All Related Tables###
def build_admissions_and_rejects(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    admission_cols_cfg = get_table_columns("admission_data") 
    admission_cols = list(admission_cols_cfg.keys())

    admission_pk_col, _ = get_pk_column_and_type("admission_data")

    admission_required_cols = [c for c in admission_cols if c != admission_pk_col]

    admissions_required = df[admission_required_cols].copy()

    required_cols = admission_required_cols

    missing_mask = admissions_required[required_cols].isna().any(axis=1)

    missing_columns_series = admissions_required[required_cols].isna().apply(
        lambda row: ",".join(row.index[row]),
        axis=1,
    )

    reject_cols = get_table_columns("rejects")
    reject_pk_col, _ = get_pk_column_and_type("rejects")

    reject_data_cols = [
        c for c in reject_cols if c not in (reject_pk_col, "missing_columns")
    ]

    rejects_df = df.loc[missing_mask, reject_data_cols].copy()
    rejects_df["missing_columns"] = missing_columns_series[missing_mask].values

    admissions_df = admissions_required[~missing_mask].reset_index(drop=True)

    admissions_df[admission_pk_col] = admissions_df.index + 1

    admissions_df = admissions_df[admission_cols]

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

    return admissions_df, rejects_df




def transform(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    logger.info(
        "Starting transform(): input df has %d rows x %d columns",
        df.shape[0],
        df.shape[1],
    )

    try:
        ###Builds Dataframe for Each Table Based On Schema###
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
        hosp_mapping = get_source_to_db_mapping("hospitals")
        hosp_source_col = next(iter(hosp_mapping.keys()))
        hosp_name_col = hosp_mapping[hosp_source_col]

        doctors_df = doctors_df.merge(
            hospitals_df[[hosp_name_col, hosp_pk_col]],
            left_on=hosp_source_col,
            right_on=hosp_name_col,
            how="left",
        )

        doctors_df = doctors_df.dropna(subset=[hosp_pk_col]).copy()
        doctors_df[hosp_pk_col] = doctors_df[hosp_pk_col].astype(int)

        if hosp_source_col in doctors_df.columns:
            doctors_df = doctors_df.drop(columns=[hosp_source_col])

        conditions_df = build_dimension_df(df, "conditions")
        insurance_df = build_dimension_df(df, "insurance")
        test_results_df = build_dimension_df(df, "test_results")

        allowed_test_results = get_enum_values_from_check(
            "test_results", "result_label"
        )

        test_results_df = test_results_df[
            test_results_df["result_label"].isin(allowed_test_results)
        ].reset_index(drop=True)

        admission_types_df = build_dimension_df(df, "admission_types")


        ###Merging###
        df = merge_dimension(df, people_df, "people")
        doctor_mapping = get_source_to_db_mapping("doctors")
        hospital_mapping = get_source_to_db_mapping("hospitals")

        doctor_name_col = doctor_mapping["doctor"]
        hospital_name_col = hospital_mapping[hosp_source_col]

        df = merge_dimension(
            df,
            doctors_df,
            "doctors",
            left_on=["doctor", hosp_source_col],
            right_on=[doctor_name_col, hospital_name_col],
        )

        df = merge_dimension(df, conditions_df, "conditions")
        df = merge_dimension(df, insurance_df, "insurance")
        df = merge_dimension(df, test_results_df, "test_results")
        df = merge_dimension(df, admission_types_df, "admission_types")

        logger.info(
            "Finished merges; df is now %d rows x %d columns",
            df.shape[0],
            df.shape[1],
        )

        ###Building Admissions and Results DF's and Handling NA Columns in Rejects###
        admissions_df, rejects_df = build_admissions_and_rejects(df)
        rejects_df = rejects_df.astype("object").where(pd.notna(rejects_df), None)


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
