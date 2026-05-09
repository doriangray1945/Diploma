from datetime import datetime

from pydantic import BaseModel, Field


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    text: str | None = Field(default=None, max_length=2000)


class ReviewUpdate(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    text: str | None = Field(default=None, max_length=2000)


class ReviewResponse(BaseModel):
    id: int
    user_id: int
    user_name: str
    rating: int
    text: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReviewListResponse(BaseModel):
    items: list[ReviewResponse]
    total: int


class ReviewEligibility(BaseModel):
    # True when user has at least one delivered order containing this product.
    can_review: bool
    # True when user already wrote a review for this product (one per user/product).
    has_review: bool
    # The user's own review if it exists, else None.
    my_review: ReviewResponse | None
