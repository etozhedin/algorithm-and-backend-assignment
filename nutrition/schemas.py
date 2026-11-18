from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator


def reject_bool(value):
    if isinstance(value, bool):
        raise ValueError("Boolean values are not numeric values")
    return value


Text = Annotated[str, Field(min_length=1, max_length=500)]
Code = Annotated[str, Field(min_length=1, max_length=100)]
Number = Annotated[float, BeforeValidator(reject_bool), Field(ge=0, allow_inf_nan=False)]
Year = Annotated[int, BeforeValidator(reject_bool), Field(ge=1, le=9999)]


class FoodFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, from_attributes=True)
    food_cd: Code
    food_name: Text
    group_name: Text | None = None
    research_year: Year | None = None
    maker_name: Text | None = None
    ref_name: Text | None = None
    serving_size: Number | None = None
    calorie: Number | None = None
    carbohydrate: Number | None = None
    protein: Number | None = None
    fat: Number | None = None
    sugars: Number | None = None
    sodium: Number | None = None
    cholesterol: Number | None = None
    saturated_fatty_acids: Number | None = None
    trans_fat: Number | None = None


class FoodCreate(FoodFields):
    pass


class FoodUpdate(FoodFields):
    food_cd: Code | None = None
    food_name: Text | None = None

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        for field in ("food_cd", "food_name"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class FoodResponse(FoodFields):
    id: int


class FoodPage(BaseModel):
    items: list[FoodResponse]
    total: int
    page: int
    page_size: int


class FoodSearch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    food_name: Text | None = None
    research_year: Year | None = None
    maker_name: Text | None = None
    food_code: Code | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[dict] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
