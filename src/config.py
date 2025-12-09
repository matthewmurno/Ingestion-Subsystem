from pathlib import Path
import os
import yaml
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT_DIR / "config" / "sources.yml"
SCHEMAS_CONFIG_PATH = ROOT_DIR / "config" / "schemas.yml"
RULES_CONFIG_PATH = ROOT_DIR / "config" / "rules.yml"

load_dotenv(ROOT_DIR / ".env")

def load_config(path=None, schemas_path=None):
    if path is None:
        path = DEFAULT_CONFIG_PATH
    if schemas_path is None:
        schemas_path = SCHEMAS_CONFIG_PATH

    path = Path(path)

    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    db_url = config["defaults"].get("db_url")
    if isinstance(db_url, str):
        config["defaults"]["db_url"] = os.path.expandvars(db_url)

    schemas_path = Path(schemas_path)
    if schemas_path.exists():
        with schemas_path.open("r", encoding="utf-8") as f:
            schemas_cfg = yaml.safe_load(f) or {}
        schemas = schemas_cfg.get("schemas", schemas_cfg) or {}
        config["schemas"] = schemas

    return config
CONFIG = load_config()

def get_source_config(name) -> dict:
    for source in CONFIG.get("sources", []):
        if source.get("name") == name:
            return source
    raise KeyError(f"Source config not found for name={name!r}")

def get_schema(table_name) -> dict:
    try:
        return CONFIG["schemas"][table_name]
    except KeyError:
        raise KeyError(f"Schema not found for table={table_name!r}")

def get_table_columns(table_name) -> dict:
    schema = get_schema(table_name)
    return schema.get("columns", {})


def get_not_null_columns(table_name) -> list[str]:
    cols = get_table_columns(table_name)
    return [name for name, meta in cols.items() if meta.get("not_null")]

def get_source_not_null_columns(table_name) -> list[str]:
    cols = get_table_columns(table_name)
    result: list[str] = []

    for db_col, meta in cols.items():
        if meta.get("primary_key"):
            continue

        if meta.get("not_null"):
            if "source" in meta and meta["source"] is not None:
                result.append(meta["source"])

    return result

def get_source_to_db_mapping(table_name: str) -> dict[str, str]:
    cols = get_table_columns(table_name)
    mapping: dict[str, str] = {}
    for db_col, meta in cols.items():
        source_col = meta.get("source")
        if source_col:
            mapping[source_col] = db_col
    return mapping

def get_pk_column_and_type(table_name) -> tuple[str, str]:
    cols = get_table_columns(table_name)
    for name, meta in cols.items():
        if meta.get("primary_key"):
            return name, meta["type"]
    raise KeyError(f"No primary_key defined for table={table_name!r} in schemas.yml")


def get_enum_values_from_check(table_name, column_name) -> list[str]:
    cols = get_table_columns(table_name)
    meta = cols.get(column_name, {})
    check_expr = meta.get("check")
    if not check_expr:
        return []

    if "IN" not in check_expr:
        return []

    inside = check_expr.split("IN", 1)[1].strip()
    inside = inside.lstrip("(").rstrip(")").strip()
    values = [v.strip().strip("'") for v in inside.split(",")]
    return values

def _load_rules_config(path: str | Path | None = None) -> dict:
    if path is None:
        path = RULES_CONFIG_PATH

    path = Path(path)
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    if "rules" in cfg:
        return cfg["rules"]
    return cfg


RULES_CONFIG = _load_rules_config()

def get_cleaning_rules() -> dict:
    rules_block = RULES_CONFIG or {}
    return rules_block.get("columns", {})