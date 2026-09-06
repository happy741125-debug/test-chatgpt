from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DomainCode(StrEnum):
    WAREHOUSE_OPERATIONS = "WAREHOUSE_OPERATIONS"
    CUSTOMER = "CUSTOMER"
    SALES = "SALES"
    FINANCE_COST = "FINANCE_COST"
    PEOPLE = "PEOPLE"
    ALLIANCE_WAREHOUSE = "ALLIANCE_WAREHOUSE"
    SYSTEM = "SYSTEM"
    MANAGEMENT = "MANAGEMENT"
    UNKNOWN = "UNKNOWN"


class IntelligenceType(StrEnum):
    EVENT = "EVENT"
    TASK = "TASK"
    COMMITMENT = "COMMITMENT"
    DECISION = "DECISION"
    DECISION_REQUIRED = "DECISION_REQUIRED"
    RISK = "RISK"
    FOLLOW_UP = "FOLLOW_UP"
    FYI = "FYI"


class NoiseType(StrEnum):
    GENERAL_CHAT = "GENERAL_CHAT"
    STICKER = "STICKER"
    ADVERTISEMENT = "ADVERTISEMENT"
    AUTOMATED = "AUTOMATED"
    UNREADABLE = "UNREADABLE"
    DUPLICATE = "DUPLICATE"


class EntityType(StrEnum):
    PERSON = "PERSON"
    COMPANY = "COMPANY"
    CUSTOMER = "CUSTOMER"
    PROJECT = "PROJECT"
    PRODUCT = "PRODUCT"
    LOCATION = "LOCATION"
    VENDOR = "VENDOR"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EntityMention(StrictModel):
    type: EntityType
    text: str = Field(min_length=1, max_length=255)
    evidence_message_id: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class DeadlineValue(StrictModel):
    raw_text: str = Field(min_length=1, max_length=255)
    resolved_at: datetime | None = None
    timezone: str = "Asia/Taipei"
    confidence: float = Field(ge=0, le=1)


class IntelligenceItem(StrictModel):
    type: IntelligenceType
    domain_code: DomainCode
    event_type_code: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1, max_length=2000)
    owner_text: str | None = Field(default=None, max_length=255)
    deadline: DeadlineValue | None = None
    requires_user_action: bool = False
    evidence_message_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class ContextAnalysisOutput(StrictModel):
    work_related: bool
    noise_type: NoiseType | None = None
    summary: str = Field(min_length=1, max_length=2000)
    entities: list[EntityMention] = Field(default_factory=list)
    items: list[IntelligenceItem] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def work_and_noise_are_consistent(self) -> ContextAnalysisOutput:
        if self.work_related and not self.items:
            raise ValueError("work-related output must contain at least one intelligence item")
        if self.work_related and self.noise_type is not None:
            raise ValueError("work-related output cannot have a noise type")
        if not self.work_related and self.items:
            raise ValueError("noise output cannot contain intelligence items")
        if not self.work_related and self.noise_type is None:
            raise ValueError("noise output must include a noise type")
        return self
