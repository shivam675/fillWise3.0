"""Ruleset Pydantic schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RuleDefinition(BaseModel):
    """A single rule within a ruleset."""

    id: str = Field(
        ..., description="Stable machine identifier for this rule, e.g. 'rule-1'"
    )
    name: str
    instruction: str = Field(
        ...,
        description="Plain-language instruction that applies to all text sections",
    )


class RuleOut(BaseModel):
    id: str
    name: str
    instruction: str


class CreateRulesetRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=255)
    description: str = Field(default="", max_length=2000)
    jurisdiction: str | None = Field(default=None, max_length=100)
    version: str = Field(
        ..., min_length=1, max_length=50, description="Semantic version, e.g. '1.0.0'"
    )
    rules: list[RuleDefinition] = Field(..., min_length=1)


class RulesetOut(BaseModel):
    id: str
    name: str
    description: str
    jurisdiction: str | None
    version: str
    schema_version: str
    content_hash: str
    is_active: bool
    rules: list[RuleOut] = Field(default_factory=list)
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RulesetListResponse(BaseModel):
    items: list[RulesetOut]
    total: int


class RuleConflictOut(BaseModel):
    rule_a_id: str
    rule_b_id: str
    description: str
    is_resolved: bool

    model_config = {"from_attributes": True}


class ActivateRulesetResponse(BaseModel):
    id: str
    is_active: bool
    message: str
