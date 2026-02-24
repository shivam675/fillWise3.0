"""Ruleset management API endpoints."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Annotated

import structlog
import yaml
from fastapi import APIRouter, Depends, Query, Request, UploadFile
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.api.deps import AdminUser, CurrentUser, EditorUser, ReviewerUser, get_db
from app.core.errors import ConflictError, ErrorCode, NotFoundError, ValidationError
from app.db.models.ruleset import RuleConflict, Ruleset
from app.schemas.ruleset import (
    ActivateRulesetResponse,
    CreateRulesetRequest,
    RuleConflictOut,
    RulesetListResponse,
    RulesetOut,
)
from app.services.audit.logger import AuditLogger
from app.services.rules.validator import (
    compute_rules_hash,
    detect_rule_conflicts,
    validate_ruleset_dict,
)

_log = structlog.get_logger(__name__)
router = APIRouter(prefix="/rulesets", tags=["rulesets"])


def _to_ruleset_out(rs: Ruleset) -> RulesetOut:

    raw_rules: list[dict[str, object]] = []
    try:
        parsed = json.loads(rs.rules_json or "[]")
        if isinstance(parsed, list):
            raw_rules = [r for r in parsed if isinstance(r, dict)]
    except Exception:
        raw_rules = []

    rules = [
        {
            "id": str(rule.get("id", "")),
            "name": str(rule.get("name", "")),
            "instruction": str(rule.get("instruction", "")),
        }
        for rule in raw_rules
    ]

    return RulesetOut(
        id=rs.id,
        name=rs.name,
        description=rs.description,
        jurisdiction=rs.jurisdiction,
        version=rs.version,
        schema_version=rs.schema_version,
        content_hash=rs.content_hash,
        is_active=rs.is_active,
        rules=rules,
        created_by=rs.created_by,
        created_at=rs.created_at,
        updated_at=rs.updated_at,
    )


async def _resolve_create_body(
    request: Request,
) -> CreateRulesetRequest:
    content_type = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" not in content_type:
        try:
            payload = await request.json()
        except Exception as exc:
            raise ValidationError("Invalid JSON body") from exc

        try:
            return CreateRulesetRequest.model_validate(payload)
        except PydanticValidationError as exc:
            raise ValidationError("JSON does not match ruleset schema", detail={"errors": exc.errors()}) from exc

    form = await request.form()
    file_obj = form.get("file")
    if not isinstance(file_obj, (UploadFile, StarletteUploadFile)):
        raise ValidationError("Multipart upload must include a 'file' field")

    filename = (file_obj.filename or "").lower()
    if not filename.endswith((".yaml", ".yml", ".json")):
        raise ValidationError("Only .yaml, .yml, or .json files are supported")

    raw_bytes = await file_obj.read()
    if not raw_bytes:
        raise ValidationError("Uploaded YAML file is empty")

    try:
        parsed = yaml.safe_load(raw_bytes.decode("utf-8"))
    except Exception as exc:
        raise ValidationError("Invalid YAML file", detail={"error": str(exc)}) from exc

    if not isinstance(parsed, Mapping):
        raise ValidationError("YAML root must be an object/mapping")

    try:
        return CreateRulesetRequest.model_validate(dict(parsed))
    except PydanticValidationError as exc:
        raise ValidationError("YAML does not match ruleset schema", detail={"errors": exc.errors()}) from exc


@router.post(
    "",
    response_model=RulesetOut,
    status_code=201,
    summary="Create a new ruleset",
    dependencies=[EditorUser],
)
async def create_ruleset(
    request: Request,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RulesetOut:
    """
    Create and store a new ruleset.

    Validates the rule schema, detects conflicts, and stores the ruleset
    in inactive state. Rules must be explicitly activated before use.
    """
    resolved_body = await _resolve_create_body(request)

    rules_list = [r.model_dump(exclude_none=True) for r in resolved_body.rules]
    full_dict = {
        "name": resolved_body.name,
        "description": resolved_body.description,
        "version": resolved_body.version,
        "jurisdiction": resolved_body.jurisdiction,
        "rules": rules_list,
    }

    schema_errors = validate_ruleset_dict(full_dict)
    if schema_errors:
        raise ValidationError(
            "Ruleset failed schema validation",
            detail={"errors": schema_errors},
        )

    content_hash = compute_rules_hash(full_dict)

    # Check version uniqueness
    existing = await db.execute(
        select(Ruleset).where(
            Ruleset.name == resolved_body.name,
            Ruleset.version == resolved_body.version,
            Ruleset.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError(
            ErrorCode.RULE_VERSION_CONFLICT,
            f"Ruleset '{resolved_body.name}' version '{resolved_body.version}' already exists.",
        )

    ruleset = Ruleset(
        name=resolved_body.name,
        description=resolved_body.description or "",
        jurisdiction=resolved_body.jurisdiction,
        version=resolved_body.version,
        schema_version="1.0",
        content_hash=content_hash,
        is_active=False,
        rules_json=json.dumps(rules_list),
        created_by=current_user.id,
    )
    db.add(ruleset)
    await db.flush()

    # Detect and store conflicts
    conflicts = detect_rule_conflicts(rules_list)
    for c in conflicts:
        db.add(
            RuleConflict(
                ruleset_id=ruleset.id,
                rule_a_id=c["rule_a_id"],
                rule_b_id=c["rule_b_id"],
                description=c["description"],
            )
        )

    audit = AuditLogger(db)
    await audit.log(
        event_type="ruleset.created",
        actor_id=current_user.id,
        actor_username=current_user.username,
        entity_type="Ruleset",
        entity_id=ruleset.id,
        payload={
            "name": resolved_body.name,
            "version": resolved_body.version,
            "conflicts": len(conflicts),
        },
    )
    await db.commit()

    if conflicts:
        _log.warning(
            "ruleset_created_with_conflicts",
            ruleset_id=ruleset.id,
            conflicts=len(conflicts),
        )

    return _to_ruleset_out(ruleset)


@router.get(
    "",
    response_model=RulesetListResponse,
    summary="List rulesets",
    dependencies=[ReviewerUser],
)
async def list_rulesets(
    db: Annotated[AsyncSession, Depends(get_db)],
    active_only: bool = Query(default=False),
) -> RulesetListResponse:
    query = select(Ruleset).where(Ruleset.deleted_at.is_(None))
    if active_only:
        query = query.where(Ruleset.is_active.is_(True))

    count = await db.execute(select(func.count()).select_from(query.subquery()))
    result = await db.execute(query.order_by(Ruleset.created_at.desc()))
    return RulesetListResponse(
        items=[_to_ruleset_out(r) for r in result.scalars().all()],
        total=count.scalar_one(),
    )


@router.get(
    "/{ruleset_id}",
    response_model=RulesetOut,
    summary="Get ruleset details",
    dependencies=[ReviewerUser],
)
async def get_ruleset(
    ruleset_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RulesetOut:
    rs = await db.get(Ruleset, ruleset_id)
    if rs is None or rs.is_deleted:
        raise NotFoundError("Ruleset", ruleset_id)
    return _to_ruleset_out(rs)


@router.get(
    "/{ruleset_id}/conflicts",
    response_model=list[RuleConflictOut],
    summary="List rule conflicts",
    dependencies=[ReviewerUser],
)
async def get_conflicts(
    ruleset_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[RuleConflictOut]:
    rs = await db.get(Ruleset, ruleset_id)
    if rs is None or rs.is_deleted:
        raise NotFoundError("Ruleset", ruleset_id)
    result = await db.execute(
        select(RuleConflict).where(RuleConflict.ruleset_id == ruleset_id)
    )
    return [RuleConflictOut.model_validate(c) for c in result.scalars().all()]


@router.post(
    "/{ruleset_id}/activate",
    response_model=ActivateRulesetResponse,
    summary="Activate a ruleset",
    dependencies=[AdminUser],
)
async def activate_ruleset(
    ruleset_id: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ActivateRulesetResponse:
    """
    Activate a ruleset for use in rewrite jobs.

    Fails if unresolved conflicts exist.
    """
    rs = await db.get(Ruleset, ruleset_id)
    if rs is None or rs.is_deleted:
        raise NotFoundError("Ruleset", ruleset_id)

    if rs.is_active:
        raise ConflictError(ErrorCode.RULE_ALREADY_ACTIVE, "Ruleset is already active.")

    unresolved = await db.execute(
        select(RuleConflict).where(
            RuleConflict.ruleset_id == ruleset_id,
            RuleConflict.is_resolved.is_(False),
        )
    )
    if list(unresolved.scalars().all()):
        raise ConflictError(
            ErrorCode.RULE_CONFLICTS_PRESENT,
            "Cannot activate ruleset with unresolved conflicts. Resolve or dismiss them first.",
        )

    rs.is_active = True
    audit = AuditLogger(db)
    await audit.log(
        event_type="ruleset.activated",
        actor_id=current_user.id,
        actor_username=current_user.username,
        entity_type="Ruleset",
        entity_id=rs.id,
    )
    await db.commit()

    return ActivateRulesetResponse(
        id=rs.id, is_active=True, message="Ruleset activated successfully."
    )
