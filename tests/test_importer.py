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
