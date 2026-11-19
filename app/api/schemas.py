from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel

from app.models import AccountStatus, DealStatus

T = TypeVar("T")

Band = Literal["low", "medium", "high"]
SortOrder = Literal["asc", "desc"]


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# ---------- Scores ----------

class ScoreSummary(BaseModel):
    fraud_score: float
    default_score: float
    fraud_band: str
    default_band: str
    model_version: str
    computed_at: datetime


class ScoreDetail(ScoreSummary):
    top_factors: dict | list | None = None


# ---------- Deals (embedded in detail views) ----------

class CustomerDealSummary(BaseModel):
    id: int
    store_id: int
    store_name: str
    amount_sar: float
    status: DealStatus
    created_at: datetime
    closed_at: datetime | None


class StoreDealSummary(BaseModel):
    id: int
    customer_id: int
    amount_sar: float
    status: DealStatus
    created_at: datetime
    closed_at: datetime | None


# ---------- Customers ----------

class CustomerListItem(BaseModel):
    id: int
    name: str
    phone: str
    email: str
    account_status: AccountStatus
    created_at: datetime
    scores: ScoreSummary | None


class CustomerDetail(BaseModel):
    id: int
    name: str
    phone: str
    email: str
    account_status: AccountStatus
    created_at: datetime
    scores: ScoreDetail | None
    recent_deals: list[CustomerDealSummary]


# ---------- Stores ----------

class StoreListItem(BaseModel):
    id: int
    name: str
    commercial_registration_no: str
    category: str
    city: str
    account_status: AccountStatus
    created_at: datetime
    scores: ScoreSummary | None


class StoreStats(BaseModel):
    total_deals: int
    disputed_deals: int
    dispute_rate: float | None
    paid_deals: int
    refunded_deals: int
    refund_rate: float | None

    
class StoreDetail(BaseModel):
    id: int
    name: str
    commercial_registration_no: str
    category: str
    city: str
    account_status: AccountStatus
    created_at: datetime
    scores: ScoreDetail | None
    stats: StoreStats
    recent_deals: list[StoreDealSummary]