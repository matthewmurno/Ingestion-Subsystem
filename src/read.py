import pandas as pd

from src.logger import get_logger

logger = get_logger(__name__)


def read_csv(filepath: str) -> pd.DataFrame:
    logger.info("Reading CSV file from %s", filepath)
    try:
        df = pd.read_csv(filepath)
        logger.info("Successfully read CSV: %d rows x %d columns", df.shape[0], df.shape[1])
        return df
    except Exception:
        logger.exception("Failed to read CSV file from %s", filepath)
        raise


def read_json(filepath: str) -> pd.DataFrame:
    logger.info("Reading JSON file from %s", filepath)
    try:
        df = pd.read_json(filepath)
        logger.info("Successfully read JSON: %d rows x %d columns", df.shape[0], df.shape[1])
        return df
    except Exception:
        logger.exception("Failed to read JSON file from %s", filepath)
        raise


def read(source_cfg: dict) -> pd.DataFrame:
    source_type = source_cfg["type"]
    path = source_cfg["path"]

    logger.info("Starting read() for type=%s, path=%s", source_type, path)

    if source_type == "csv":
        return read_csv(path)
    elif source_type == "json":
        return read_json(path)
    else:
        logger.error("Unsupported source type in read(): %s", source_type)
        raise ValueError(f"Unsupported source type: {source_type}")