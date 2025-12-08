import pandas as pd
from src.logger import get_logger
from src.config import get_cleaning_rules

logger = get_logger(__name__)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    logger.info(
        "Starting clean(): input df has %d rows x %d columns",
        df.shape[0],
        df.shape[1],
    )

    df = df.copy()
    rules = get_cleaning_rules() 

    try:
        ###Converting Column Names to snake_case for Normalizaiton###
        original_cols = list(df.columns)
        df = df.rename(columns=lambda col: col.lower().strip().replace(" ", "_"))
        logger.debug(
            "Normalized column names. Before: %s | After: %s",
            original_cols,
            list(df.columns),
        )

        ###Striping White Space###
        str_cols = df.select_dtypes(include=["object", "string"]).columns
        logger.debug("Stripping whitespace from string columns: %s", list(str_cols))
        df[str_cols] = df[str_cols].apply(lambda s: s.str.strip())

        ###Replace Empty String to NA###
        if len(str_cols) > 0:
            empty_before = (df[str_cols] == "").sum().sum()
            df[str_cols] = df[str_cols].replace("", pd.NA)
            if empty_before > 0:
                logger.info(
                    "Converted %d empty string value(s) to NA in string columns",
                    empty_before,
                )

        ###Changing Case w/ rules.yml (UPPER, lower, Title)###
        for col, rule in rules.items():
            if col not in df.columns:
                continue

            case = rule.get("case")
            if case and pd.api.types.is_string_dtype(df[col]):
                if case == "upper":
                    df[col] = df[col].str.upper()
                elif case == "lower":
                    df[col] = df[col].str.lower()
                elif case == "title":
                    df[col] = df[col].str.title()
                logger.debug("Applied case=%s normalization to column %s", case, col)

        logger.info("Standardized string columns where present according to rules config.")

        ###Checking for Valid Numeric Ranges w/ rules.yml (>0, 1,000 == 1000, ect.)###
        for col, rule in rules.items():
            if col not in df.columns:
                continue

            if rule.get("numeric"):
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

                ###Checking if int is Within Range###
                min_val = rule.get("min")
                max_val = rule.get("max")
                if min_val is not None or max_val is not None:
                    invalid_mask = pd.Series(False, index=df.index)
                    if min_val is not None:
                        invalid_mask |= df[col] < min_val
                    if max_val is not None:
                        invalid_mask |= df[col] > max_val
                    invalid_mask &= df[col].notna()

                    invalid_count = invalid_mask.sum()
                    if invalid_count > 0:
                        logger.warning(
                            "Column %s: %d value(s) outside valid range (%s–%s); setting to NA",
                            col,
                            invalid_count,
                            min_val,
                            max_val,
                        )
                        df.loc[invalid_mask, col] = pd.NA

                round_places = rule.get("round")
                if round_places is not None and pd.api.types.is_numeric_dtype(df[col]):
                    df[col] = df[col].round(round_places)
                    logger.info(
                        "Rounded column %s to %d decimal place(s).",
                        col,
                        round_places,
                    )

        ###Checking If Dates can be processed as Datetime)###
        for col, rule in rules.items():
            if col not in df.columns:
                continue

            if rule.get("datetime"):
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

        ###Checking if Test_Results Contains Disallowed Values###
        for col, rule in rules.items():
            if col not in df.columns:
                continue

            allowed_values = rule.get("allowed_values")
            if allowed_values:
                invalid_mask = df[col].notna() & ~df[col].isin(allowed_values)
                invalid_count = invalid_mask.sum()
                if invalid_count > 0:
                    action = rule.get("invalid_action", "set_na")
                    logger.warning(
                        "Column %s: %d value(s) not in allowed_values=%s; action=%s",
                        col,
                        invalid_count,
                        allowed_values,
                        action,
                    )

                    if action == "set_na":
                        df.loc[invalid_mask, col] = pd.NA
                    elif action == "drop_row":
                        df = df.loc[~invalid_mask].copy()
                    elif action == "raise":
                        raise ValueError(
                            f"{invalid_count} invalid value(s) in column {col} "
                            f"not in {allowed_values}"
                        )

        logger.info(
            "clean() completed. Output df has %d rows x %d columns",
            df.shape[0],
            df.shape[1],
        )

        return df

    except Exception:
        logger.exception("clean() failed.")
        raise
