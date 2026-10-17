"""Pydantic schemas for structured state and ADK 2.0 task hand-offs."""

from __future__ import annotations

from typing import Any

try:
    from pydantic import AliasChoices, BaseModel, ConfigDict, Field
except ImportError:  # pragma: no cover

    class AliasChoices:  # type: ignore[no-redef]
        def __init__(self, *choices: str) -> None:
            self.choices = choices

    def ConfigDict(**kwargs: Any) -> dict[str, Any]:  # type: ignore[no-redef]
        return kwargs

    def Field(default: Any = None, **kwargs: Any) -> Any:  # type: ignore[no-redef]
        return default

    class BaseModel:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

        @classmethod
        def model_validate(cls, data: dict[str, Any]) -> Any:
            return cls(**data)

        def model_dump(self, **kwargs: Any) -> dict[str, Any]:
            return dict(self.__dict__)


class QuotaRequestTaskOutput(BaseModel):
    """Structured output returned by quota_request_agent when completing a task."""

    request_id: str = Field(description="Unique ID of the submitted or processed quota request")
    status: str = Field(description="Request lifecycle status: PENDING, CANCELLED, or ALREADY_ACTIVE")
    requested_quota_usd: float = Field(description="Target weekly quota limit in USD")
    duration_needed: str = Field(description="TEMPORARY_WEEKLY or PERMANENT")
    reason_category: str = Field(description="Normalized reason category enum")
    confirmation_message: str = Field(description="User-facing confirmation message summarizing the action")


class ConciergeState(BaseModel):
    """Typed state model representing cached session and cross-session user context."""

    model_config = ConfigDict(populate_by_name=True)

    user_email: str | None = Field(
        default=None,
        validation_alias=AliasChoices("user:email", "resolved_user_email", "user_email"),
        description="Resolved corporate email (user:email)",
    )
    current_quota_usd: float = Field(default=10.0, description="Current weekly quota limit in USD")
    current_spend_usd: float = Field(default=0.0, description="Current week gross spend in USD")
    user_status: str = Field(default="ACTIVE", description="ACTIVE, AUTO_DISABLED, or MANUALLY_DISABLED")
    group_id: str = Field(default="business-users", description="User's assigned group tier")
    active_request_id: str | None = Field(default=None, description="Active pending request ID if any")
    preferred_option_number: int | None = Field(
        default=None,
        validation_alias=AliasChoices("user:preferred_option", "preferred_option_number"),
        description="Preferred preset option number (1, 2, or 3)",
    )
    last_reason_category: str | None = Field(
        default=None,
        validation_alias=AliasChoices("user:last_reason_category", "last_reason_category"),
        description="Most recent reason category",
    )

