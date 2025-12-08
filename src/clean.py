import pandas as pd
from src.logger import get_logger

logger = get_logger(__name__)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    logger.info(
        "Starting clean(): input df has %d rows x %d columns",
        df.shape[0],
        df.shape[1],
    )

    df = df.copy()

    try:
        original_cols = list(df.columns)
        df = df.rename(columns=lambda col: col.lower().strip().replace(" ", "_"))
        logger.debug(
            "Normalized column names. Before: %s | After: %s",
            original_cols,
            list(df.columns),
        )

        str_cols = df.select_dtypes(include=["object", "string"]).columns
        logger.debug("Stripping whitespace from string columns: %s", list(str_cols))
        df[str_cols] = df[str_cols].apply(lambda s: s.str.strip())

        if len(str_cols) > 0:
            empty_before = (df[str_cols] == "").sum().sum()
            df[str_cols] = df[str_cols].replace("", pd.NA)
            if empty_before > 0:
                logger.info(
                    "Converted %d empty string value(s) to NA in string columns",
                    empty_before,
                )

        if "name" in df.columns:
            df["name"] = df["name"].str.title()
        if "gender" in df.columns:
            df["gender"] = df["gender"].str.upper()
        if "blood_type" in df.columns:
            df["blood_type"] = df["blood_type"].str.upper()
        if "doctor" in df.columns:
            df["doctor"] = df["doctor"].str.title()
        if "hospital" in df.columns:
            df["hospital"] = df["hospital"].str.title()
        if "insurance_provider" in df.columns:
            df["insurance_provider"] = df["insurance_provider"].str.title()
        if "medical_condition" in df.columns:
            df["medical_condition"] = df["medical_condition"].str.title()
        if "test_results" in df.columns:
            df["test_results"] = df["test_results"].str.lower()

            valid_results = ["inconclusive", "normal", "abnormal"]
            invalid_mask = df["test_results"].notna() & ~df["test_results"].isin(valid_results)
            invalid_count = invalid_mask.sum()
            if invalid_count > 0:
                logger.warning(
                    "test_results: %d value(s) not in %s; setting to NA",
                    invalid_count,
                    valid_results,
                )
                df.loc[invalid_mask, "test_results"] = pd.NA
        if "admission_type" in df.columns:
            df["admission_type"] = df["admission_type"].str.lower()
        if "medication" in df.columns:
            df["mediation"] = df["medication"].str.lower()

        logger.info("Standardized string columns where present.")

        for col in ["age", "billing_amount", "room_number"]:
            if col in df.columns:
                before_non_null = df[col].notna().sum()
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.replace(",", "", regex=False)
                    .pipe(pd.to_numeric, errors="coerce")
                )
                after_non_null = df[col].notna().sum()
                coerced = before_non_null - after_non_null

                if coerced > 0:
                    logger.warning(
                        "Column %s: %d value(s) could not be converted to numeric and were set to NaN",
                        col,
                        coerced,
                    )
                else:
                    logger.info("Column %s converted to numeric successfully.", col)

        if "age" in df.columns:
            logger.info(
                "Age range before validation: min=%s, max=%s",
                df["age"].min(),
                df["age"].max(),
            )
            invalid_age_mask = df["age"].notna() & (
                (df["age"] < 0) | (df["age"] > 120)
            )
            invalid_count = invalid_age_mask.sum()
            if invalid_count > 0:
                logger.warning(
                    "Age: %d value(s) outside valid range (0–120); setting to NA",
                    invalid_count,
                )
                df.loc[invalid_age_mask, "age"] = pd.NA

        if "room_number" in df.columns:
            logger.info(
                "Room_number range before validation: min=%s, max=%s",
                df["room_number"].min(),
                df["room_number"].max(),
            )
            invalid_room_mask = df["room_number"].notna() & (
                (df["room_number"] < 0) | (df["room_number"] > 100000)
            )
            invalid_rooms = invalid_room_mask.sum()
            if invalid_rooms > 0:
                logger.warning(
                    "room_number: %d value(s) outside valid range (0–100000); setting to NA",
                    invalid_rooms,
                )
                df.loc[invalid_room_mask, "room_number"] = pd.NA

        if "billing_amount" in df.columns:
            df["billing_amount"] = df["billing_amount"].round(2)
            logger.info("Rounded billing_amount to 2 decimal places.")

        for col in ["date_of_admission", "discharge_date"]:
            if col in df.columns:
                before_non_null = df[col].notna().sum()
                df[col] = pd.to_datetime(df[col], errors="coerce")
                after_non_null = df[col].notna().sum()
                coerced = before_non_null - after_non_null
                if coerced > 0:
                    logger.warning(
                        "Column %s: %d value(s) could not be parsed as datetime and were set to NaT",
                        col,
                        coerced,
                    )
                else:
                    logger.info("Column %s parsed as datetime successfully.", col)

        logger.info(
            "clean() completed. Output df has %d rows x %d columns",
            df.shape[0],
            df.shape[1],
        )

        return df

    except Exception:
        logger.exception("clean() failed.")
        raise
