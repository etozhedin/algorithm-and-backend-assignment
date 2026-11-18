import logging
import time
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from nutrition.db import Food, make_engine
from nutrition.schemas import (
    ErrorResponse,
    FoodCreate,
    FoodPage,
    FoodResponse,
    FoodSearch,
    FoodUpdate,
)

logger = logging.getLogger("nutrition")


def create_app(database_url=None):
    engine = make_engine(database_url)

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()

    app = FastAPI(
        title="Food Nutrition API",
        version="1.0.0",
        lifespan=lifespan,
        responses={status: {"model": ErrorResponse} for status in (404, 409, 422, 500)},
    )
    app.state.engine = engine

    def session_dependency():
        with Session(engine) as session:
            yield session

    Database = Annotated[Session, Depends(session_dependency)]

    def error_response(status, code, message, details=None):
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "details": details,
                }
            },
        )

    @app.middleware("http")
    async def trace_request(request: Request, call_next):
        request_id = str(uuid4())
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request_id=%s unhandled request failure", request_id)
            response = error_response(500, "internal_error", "An unexpected error occurred")
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            (time.monotonic() - started) * 1000,
        )
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        codes = {404: "not_found", 409: "conflict", 503: "unavailable"}
        return error_response(
            exc.status_code, codes.get(exc.status_code, "http_error"), str(exc.detail)
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        details = [
            {"location": list(e["loc"]), "message": e["msg"], "type": e["type"]}
            for e in exc.errors()
        ]
        return error_response(422, "validation_error", "Request validation failed", details)

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        logger.exception("Unhandled request failure")
        return error_response(500, "internal_error", "An unexpected error occurred")

    def get_food(session, food_id):
        food = session.get(Food, food_id)
        if food is None:
            raise HTTPException(404, "Food not found")
        return food

    def commit(session):
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(409, "Food code already exists") from None

    @app.get("/health", tags=["operations"])
    def health(session: Database):
        try:
            session.execute(select(Food.id).limit(0))
        except Exception:
            raise HTTPException(503, "Database is unavailable") from None
        return {"status": "ok"}

    @app.get("/foods", response_model=FoodPage, tags=["foods"])
    def list_foods(session: Database, query: Annotated[FoodSearch, Query()]):
        conditions = []
        for name in ("food_name", "maker_name"):
            value = getattr(query, name)
            if value is not None:
                conditions.append(getattr(Food, name).icontains(value, autoescape=True))
        if query.research_year is not None:
            conditions.append(Food.research_year == query.research_year)
        if query.food_code is not None:
            conditions.append(Food.food_cd == query.food_code)
        # Keep count and page rows in one consistent snapshot.
        if engine.dialect.name == "postgresql":
            session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        else:
            session.connection().exec_driver_sql("BEGIN")
        total = session.scalar(select(func.count()).select_from(Food).where(*conditions))
        items = session.scalars(
            select(Food)
            .where(*conditions)
            .order_by(Food.id)
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        ).all()
        return {"items": items, "total": total, "page": query.page, "page_size": query.page_size}

    @app.post("/foods", response_model=FoodResponse, status_code=201, tags=["foods"])
    def create_food(payload: FoodCreate, response: Response, session: Database):
        food = Food(**payload.model_dump())
        session.add(food)
        commit(session)
        session.refresh(food)
        response.headers["Location"] = f"/foods/{food.id}"
        return food

    @app.get("/foods/{food_id}", response_model=FoodResponse, tags=["foods"])
    def read_food(food_id: int, session: Database):
        return get_food(session, food_id)

    @app.patch("/foods/{food_id}", response_model=FoodResponse, tags=["foods"])
    def update_food(food_id: int, payload: FoodUpdate, session: Database):
        food = get_food(session, food_id)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(food, key, value)
        commit(session)
        session.refresh(food)
        return food

    @app.delete("/foods/{food_id}", status_code=204, tags=["foods"])
    def delete_food(food_id: int, session: Database):
        session.delete(get_food(session, food_id))
        commit(session)
        return Response(status_code=204)

    return app


app = create_app()
