"""Streaming, atomic, insert-only Excel import. Run: python -m nutrition.importer FILE."""

import argparse
import json
import re
from pathlib import Path

from openpyxl import load_workbook
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from nutrition.db import Food, initialize, make_engine
from nutrition.schemas import FoodCreate

# Explicit aliases; unknown layouts fail instead of silently dropping nutrient fields.
COLUMN_ALIASES = {
    "food_cd": ["식품코드", "food_cd"],
    "food_name": ["식품명", "food_name"],
    "group_name": ["식품군", "식품대분류", "group_name"],
    "research_year": ["조사년도", "조사연도", "연도", "research_year"],
    "maker_name": ["지역/제조사", "지역및제조사", "maker_name"],
    "ref_name": ["자료출처", "성분표출처", "ref_name"],
    "serving_size": ["1회제공량", "1회제공량(g)", "1회제공량(g/ml)", "serving_size"],
    "calorie": ["에너지(kcal)", "열량(kcal)", "calorie"],
    "carbohydrate": ["탄수화물(g)", "carbohydrate"],
    "protein": ["단백질(g)", "protein"],
    "fat": ["지방(g)", "fat"],
    "sugars": ["총당류(g)", "당류(g)", "sugars"],
    "sodium": ["나트륨(mg)", "sodium"],
    "cholesterol": ["콜레스테롤(mg)", "cholesterol"],
    "saturated_fatty_acids": [
        "포화지방산(g)",
        "포화지방(g)",
        "총 포화 지방산(g)",
        "saturated_fatty_acids",
    ],
    "trans_fat": ["트랜스지방산(g)", "트랜스지방(g)", "trans_fat"],
}
TEXT_FIELDS = {"food_cd", "food_name", "group_name", "maker_name", "ref_name"}
MISSING = {"", "-", "--", "n/a", "na", "null", "nd", "n.d.", "tr", "trace"}
NUMERIC = re.compile(r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?\Z")


def normalize_header(value):
    return re.sub(r"\s+", "", str(value or "")).replace("㎉", "kcal").replace("㎎", "mg")


def column_mapping(header):
    positions = {}
    for index, value in enumerate(header):
        normalized = normalize_header(value)
        if normalized:
            positions.setdefault(normalized, []).append(index)
    mapping = {}
    for field, aliases in COLUMN_ALIASES.items():
        matches = {
            index for alias in aliases for index in positions.get(normalize_header(alias), [])
        }
        if len(matches) > 1:
            raise ValueError(f"Ambiguous columns for {field}")
        if matches:
            mapping[field] = matches.pop()
    missing = set(COLUMN_ALIASES) - mapping.keys()
    if missing:
        raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
    return mapping


def convert(value, field):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field}: boolean cell is invalid")
    if isinstance(value, str):
        value = value.strip()
        if value.casefold() in MISSING:
            return None
    if field in {"protein", "sugars", "carbohydrate"} and value == "1g 미만":
        return None
    if field in TEXT_FIELDS:
        return str(value)
    if isinstance(value, str):
        if not NUMERIC.fullmatch(value):
            raise ValueError(f"{field}: invalid numeric value {value!r}")
        return value.replace(",", "")
    return value


def import_workbook(path: Path, engine, *, sheet=None, header_row=1, batch_size=500):
    if batch_size < 1 or header_row < 1:
        raise ValueError("batch_size and header_row must be positive")
    workbook = load_workbook(path, read_only=True, data_only=True)
    stats = {"inserted": 0, "skipped": 0}
    try:
        worksheet = workbook[sheet] if sheet else workbook.worksheets[0]
        # This source incorrectly declares A1 as its entire worksheet dimension.
        # Read actual XML cells instead of trusting producer-supplied dimensions.
        worksheet.reset_dimensions()
        rows = worksheet.iter_rows(min_row=header_row, values_only=True)
        mapping = column_mapping(next(rows, ()))
        with engine.begin() as connection:
            # Begin explicitly: even errors before the first DML retain atomic semantics.
            if engine.dialect.name == "sqlite":
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            insert = pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
            batch = []

            def flush():
                result = connection.execute(
                    insert(Food)
                    .values(batch)
                    .on_conflict_do_nothing(index_elements=["food_cd"])
                    .returning(Food.id)
                )
                inserted = len(result.all())
                stats["inserted"] += inserted
                stats["skipped"] += len(batch) - inserted
                batch.clear()

            for row_number, values in enumerate(rows, start=header_row + 1):
                if all(value is None or str(value).strip() == "" for value in values):
                    continue
                try:
                    converted = {
                        field: convert(values[index] if index < len(values) else None, field)
                        for field, index in mapping.items()
                    }
                    batch.append(FoodCreate.model_validate(converted).model_dump())
                except (ValueError, ValidationError) as exc:
                    raise ValueError(f"Invalid data at row {row_number}: {exc}") from exc
                if len(batch) >= batch_size:
                    flush()
            if batch:
                flush()
        return stats
    finally:
        workbook.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--sheet", help="Worksheet name (default: first worksheet)")
    parser.add_argument("--header-row", type=int, default=1)
    args = parser.parse_args()
    engine = make_engine()
    try:
        initialize(engine)
        stats = import_workbook(args.file, engine, sheet=args.sheet, header_row=args.header_row)
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, f"Import failed: {exc}\n")
    finally:
        engine.dispose()
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
