"""End-to-end verification against the exact workbook supplied for the assignment."""

from pathlib import Path

from nutrition.importer import import_workbook

SOURCE = Path(__file__).resolve().parent.parent / "data/통합_식품영양성분DB_음식_20230715.xlsx"


def test_full_source_import_repeat_and_api(app, client):
    assert SOURCE.is_file(), "The original assignment workbook must be included in data/"
    assert import_workbook(SOURCE, app.state.engine) == {"inserted": 7683, "skipped": 0}
    assert import_workbook(SOURCE, app.state.engine) == {"inserted": 0, "skipped": 7683}
    assert client.get("/foods").json()["total"] == 7683
    result = client.get(
        "/foods",
        params={
            "food_code": "D000006",
            "food_name": "꿩불고기",
            "research_year": 2019,
            "maker_name": "충주",
            "page_size": 1,
        },
    ).json()
    assert result["total"] == 1
    food = result["items"][0]
    assert {key: value for key, value in food.items() if key != "id"} == {
        "food_cd": "D000006",
        "food_name": "꿩불고기",
        "group_name": "구이류",
        "research_year": 2019,
        "maker_name": "충주",
        "ref_name": "외식영양성분자료집 통합본(2012-2017년)",
        "serving_size": 500.0,
        "calorie": 368.8,
        "carbohydrate": 39.7,
        "protein": 33.5,
        "fat": 8.5,
        "sugars": 16.9,
        "sodium": 1264.31,
        "cholesterol": 106.18,
        "saturated_fatty_acids": 1.9,
        "trans_fat": 0.1,
    }
    assert client.get(f"/foods/{food['id']}").json() == food
    assert client.get("/foods", params={"food_name": "김치"}).json()["total"] > 0
