import pytest
from openpyxl import Workbook
from sqlalchemy import select

from nutrition.db import Food
from nutrition.importer import import_workbook

HEADERS = [
    "식품코드",
    "식품명",
    "식품군",
    "조사년도",
    "지역 / 제조사",
    "자료출처",
    "1회제공량",
    "에너지(㎉)",
    "탄수화물(g)",
    "단백질(g)",
    "지방(g)",
    "총당류(g)",
    "나트륨(㎎)",
    "콜레스테롤(㎎)",
    "포화지방산(g)",
    "트랜스지방(g)",
]


def workbook(tmp_path, rows, headers=None):
    path = tmp_path / "foods.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(headers or HEADERS)
    for row in rows:
        ws.append(row)
    wb.save(path)
    wb.close()
    return path


def row(code="D001", calorie="1,234.5"):
    return [
        code,
        "김치찌개",
        "찌개류",
        "2023",
        "서울",
        "식약처",
        "100",
        calorie,
        "-",
        "N/A",
        "",
        "Tr",
        "0",
        None,
        "0.5",
        "0",
    ]


def test_import_idempotency_and_search(app, client, tmp_path):
    path = workbook(tmp_path, [row(), row(), [None] * len(HEADERS)])
    assert import_workbook(path, app.state.engine) == {"inserted": 1, "skipped": 1}
    assert import_workbook(path, app.state.engine) == {"inserted": 0, "skipped": 2}
    response = client.get("/foods", params={"food_name": "김치", "research_year": 2023})
    assert response.json()["total"] == 1
    food = response.json()["items"][0]
    assert food["calorie"] == 1234.5
    assert food["carbohydrate"] is None
    assert food["protein"] is None
    assert food["sugars"] is None
    assert food["sodium"] == 0
    assert food["serving_size"] == 100
    assert set(food) == {
        "id",
        "food_cd",
        "group_name",
        "food_name",
        "research_year",
        "maker_name",
        "ref_name",
        "serving_size",
        "calorie",
        "carbohydrate",
        "protein",
        "fat",
        "sugars",
        "sodium",
        "cholesterol",
        "saturated_fatty_acids",
        "trans_fat",
    }


def test_import_preserves_existing_records(app, client, tmp_path, food):
    client.post("/foods", json=food)
    path = workbook(tmp_path, [row(calorie=999)])
    assert import_workbook(path, app.state.engine)["skipped"] == 1
    assert client.get("/foods").json()["items"][0]["calorie"] == food["calorie"]


@pytest.mark.parametrize("bad", ["abc", "<0.1", "100g", -1, "NaN", "Infinity"])
def test_invalid_numeric_rolls_back_entire_import(app, tmp_path, bad):
    path = workbook(tmp_path, [row(), row("D002", bad)])
    with pytest.raises(ValueError, match="row 3"):
        import_workbook(path, app.state.engine, batch_size=1)
    with app.state.engine.connect() as connection:
        assert connection.execute(select(Food)).all() == []


def test_missing_required_headers(app, tmp_path):
    path = workbook(tmp_path, [["D001", "rice"]], ["식품코드", "식품명"])
    with pytest.raises(ValueError, match="Missing columns"):
        import_workbook(path, app.state.engine)


def test_missing_required_cell(app, tmp_path):
    values = row()
    values[1] = None
    path = workbook(tmp_path, [values])
    with pytest.raises(ValueError, match="row 2"):
        import_workbook(path, app.state.engine)


def test_original_workbook_headers(app, client, tmp_path):
    headers = [
        "식품코드",
        "식품명",
        "식품대분류",
        "연도",
        "지역 / 제조사",
        "성분표출처",
        "1회제공량",
        "에너지(㎉)",
        "탄수화물(g)",
        "단백질(g)",
        "지방(g)",
        "총당류(g)",
        "나트륨(㎎)",
        "콜레스테롤(㎎)",
        "총 포화 지방산(g)",
        "트랜스 지방산(g)",
    ]
    path = workbook(tmp_path, [row()], headers)
    assert import_workbook(path, app.state.engine)["inserted"] == 1
    food = client.get("/foods").json()["items"][0]
    assert food["research_year"] == 2023
    assert food["ref_name"] == "식약처"
    assert food["saturated_fatty_acids"] == 0.5


def test_incorrect_worksheet_dimensions(app, tmp_path):
    import re
    from zipfile import ZipFile

    from openpyxl import load_workbook

    path = workbook(tmp_path, [row(), row("D002")])
    with ZipFile(path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    xml_path = "xl/worksheets/sheet1.xml"
    entries[xml_path], replacements = re.subn(
        rb"<dimension\b[^>]*/>", b'<dimension ref="A1"/>', entries[xml_path]
    )
    assert replacements == 1
    with ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    wb = load_workbook(path, read_only=True)
    assert wb.worksheets[0].max_column == 1
    assert wb.worksheets[0].max_row == 1
    wb.close()
    assert import_workbook(path, app.state.engine) == {"inserted": 2, "skipped": 0}


@pytest.mark.parametrize("field_index", [8, 9, 11])
def test_source_less_than_one_gram_is_unknown(app, client, tmp_path, field_index):
    values = row()
    values[field_index] = "1g 미만"
    path = workbook(tmp_path, [values])
    assert import_workbook(path, app.state.engine)["inserted"] == 1
    response = client.get("/foods").json()["items"][0]
    assert response[{8: "carbohydrate", 9: "protein", 11: "sugars"}[field_index]] is None
