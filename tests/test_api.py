import pytest


def test_crud(client, food):
    response = client.post("/foods", json=food)
    assert response.status_code == 201
    created = response.json()
    assert response.headers["location"] == f"/foods/{created['id']}"
    assert {key: created[key] for key in food} == food
    path = response.headers["location"]
    assert client.get(path).json() == created
    updated = client.patch(path, json={"calorie": 60, "ref_name": None})
    assert updated.status_code == 200
    assert updated.json()["calorie"] == 60
    assert updated.json()["ref_name"] is None
    assert updated.json()["food_name"] == food["food_name"]
    assert client.delete(path).status_code == 204
    for method in ["get", "patch", "delete"]:
        kwargs = {"json": {"food_name": "new"}} if method == "patch" else {}
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


def test_duplicate_and_update_conflict(client, food):
    client.post("/foods", json=food)
    assert client.post("/foods", json=food).status_code == 409
    other = client.post("/foods", json={**food, "food_cd": "D002"}).json()
    response = client.patch(f"/foods/{other['id']}", json={"food_cd": "D001"})
    assert response.status_code == 409
    assert client.get(f"/foods/{other['id']}").json()["food_cd"] == "D002"


def test_combined_search_and_pagination(client, food):
    for i in range(5):
        assert client.post("/foods", json={**food, "food_cd": f"D{i}"}).status_code == 201
    client.post("/foods", json={**food, "food_cd": "OTHER", "research_year": 2022})
    query = {
        "food_name": " 김치 ",
        "research_year": 2023,
        "maker_name": " 서울 ",
        "page": 2,
        "page_size": 2,
    }
    result = client.get("/foods", params=query).json()
    assert result["total"] == 5
    assert [f["food_cd"] for f in result["items"]] == ["D2", "D3"]
    assert result["page"] == 2
    assert result["page_size"] == 2
    assert client.get("/foods", params={"food_code": " D0 "}).json()["total"] == 1
    assert client.get("/foods", params={"food_code": "D"}).json()["total"] == 0
    assert client.get("/foods", params={"page": 50}).json()["items"] == []
    assert client.get("/foods", params={"food_name": "missing"}).json()["total"] == 0


def test_search_literal_wildcards_and_case(client, food):
    client.post("/foods", json={**food, "food_name": "ABC%_food"})
    assert client.get("/foods", params={"food_name": "abc%_"}).json()["total"] == 1
    assert client.get("/foods", params={"food_name": "%missing"}).json()["total"] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"food_name": " "},
        {"food_cd": None},
        {"calorie": -1},
        {"protein": "bad"},
        {"sodium": True},
        {"research_year": 2023.5},
        {"research_year": 0},
        {"unexpected": 1},
        {"food_cd": "x" * 101},
        {"food_name": 123},
    ],
)
def test_invalid_create(client, food, change):
    response = client.post("/foods", json={**food, **change})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    "patch", [{}, {"food_name": None}, {"food_cd": " "}, {"fat": -1}, {"extra": True}]
)
def test_invalid_patch(client, food, patch):
    created = client.post("/foods", json=food).json()
    assert client.patch(f"/foods/{created['id']}", json=patch).status_code == 422


@pytest.mark.parametrize(
    "query",
    ["page=0", "page_size=101", "page_size=-1", "research_year=abc", "unknown=1", "food_name=%20"],
)
def test_invalid_query(client, query):
    assert client.get(f"/foods?{query}").status_code == 422


def test_malformed_json_and_health(client):
    response = client.post("/foods", content="{", headers={"content-type": "application/json"})
    assert response.status_code == 422
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/unknown").json()["error"]["code"] == "not_found"
    assert client.get("/openapi.json").status_code == 200


def test_filters_use_and_and_exact_code_case(client, food):
    client.post("/foods", json=food)
    assert client.get("/foods", params={"maker_name": "부산"}).json()["total"] == 0
    assert client.get("/foods", params={"food_code": "d001"}).json()["total"] == 0
    assert (
        client.get("/foods", params={"food_name": "김치", "research_year": 2022}).json()["total"]
        == 0
    )
    assert client.get("/foods", params={"food_name": "' OR 1=1 --"}).json()["total"] == 0


def test_request_tracking(client):
    from uuid import UUID

    for path in ("/health", "/foods/999", "/foods?page=0"):
        response = client.get(path)
        assert UUID(response.headers["X-Request-ID"])
