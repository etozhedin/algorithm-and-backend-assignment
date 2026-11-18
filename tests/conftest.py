import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from nutrition.db import initialize, make_engine
from nutrition.main import create_app


@pytest.fixture
def app(tmp_path):
    database_url = os.getenv("TEST_DATABASE_URL")
    admin = None
    schema = None
    if database_url:
        # Each test owns a temporary schema; never drop an existing database or table.
        admin = make_engine(database_url)
        schema = f"test_{uuid4().hex}"
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        database_url = (
            make_url(database_url)
            .update_query_dict({"options": f"-csearch_path={schema},public"})
            .render_as_string(hide_password=False)
        )
    else:
        database_url = f"sqlite:///{tmp_path / 'test.db'}"
    app = create_app(database_url)
    try:
        initialize(app.state.engine)
        yield app
    finally:
        app.state.engine.dispose()
        if admin:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def food():
    return {
        "food_cd": "D001",
        "food_name": "김치찌개",
        "group_name": "찌개류",
        "research_year": 2023,
        "maker_name": "서울",
        "ref_name": "식약처",
        "serving_size": 100,
        "calorie": 50.5,
        "carbohydrate": 5,
        "protein": 3,
        "fat": 2,
        "sugars": 1,
        "sodium": 400,
        "cholesterol": 0,
        "saturated_fatty_acids": 0.5,
        "trans_fat": 0,
    }
