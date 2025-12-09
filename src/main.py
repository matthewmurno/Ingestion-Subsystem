from src.read import read
from src.transform import transform
from src.load import load
from src.clean import clean
from src.config import CONFIG, get_source_config

def main():
    db_url = CONFIG["defaults"]["db_url"]
    batch_size = CONFIG["defaults"]["batch_size"]
    load_mode = CONFIG["defaults"]["load_mode"]

    healthcare_cfg = get_source_config("healthcare_csv")

    raw_df = read(healthcare_cfg)
    cleaned_data = clean(raw_df)

    transformed_data = transform(cleaned_data)

    load(
        transformed_data,
        db_url=db_url,
        mode=load_mode,
        batch_size=batch_size,
    )


if __name__ == "__main__":
    main()
