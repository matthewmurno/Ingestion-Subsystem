import time

from src.logger import get_logger
from src.read import read
from src.transform import transform
from src.load import load
from src.clean import clean
from src.config import CONFIG, get_source_config



logger = get_logger(__name__)

def main():
    db_url = CONFIG["defaults"]["db_url"]
    batch_size = CONFIG["defaults"]["batch_size"]
    load_mode = CONFIG["defaults"]["load_mode"]

    healthcare_cfg = get_source_config("healthcare_csv")

    raw_df = read(healthcare_cfg)

    cleaned_data = clean(raw_df)

    time_transform_start = time.perf_counter()
    transformed_data = transform(cleaned_data)
    time_transform_end = time.perf_counter()

    time_load_start = time.perf_counter()
    load(
        transformed_data,
        db_url=db_url,
        mode=load_mode,
        batch_size=batch_size,
    )
    time_load_end = time.perf_counter()

    transform_duration = time_transform_end - time_transform_start
    load_duration = time_load_end - time_load_start

    total_loaded = len(transformed_data["admissions"])
    total_rejects = len(transformed_data["rejects"])

    rows_per_sec = total_loaded / load_duration if load_duration > 0 else 0
    rejects_per_sec = total_rejects / load_duration if load_duration > 0 else 0

    logger.info(
        "ETL metrics: total_loaded=%d, total_rejects=%d, "
        "transform_sec=%.3f, load_sec=%.3f, rows_per_sec=%.2f, rejects_per_sec=%.2f",
        total_loaded,
        total_rejects,
        transform_duration,
        load_duration,
        rows_per_sec,
        rejects_per_sec,
    )


if __name__ == "__main__":
    main()
