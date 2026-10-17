"""Compatibility layer for Google ADK (`google-adk`) imports.

When running on Vertex AI Agent Engine or with `google-adk` installed (`adk web`),
uses the official `LlmAgent` and `ToolContext` classes from `google.adk`.
When imported in lightweight test environments without `google-adk` installed,
provides structurally identical fallback classes so tools, instructions, and
multi-agent wiring can be unit-tested without external runtime dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

try:
    from google.adk.agents import LlmAgent  # type: ignore[import-untyped]
    from google.adk.tools.tool_context import ToolContext as _RealToolContext  # type: ignore[import-untyped]

    ADK_AVAILABLE = True

    class ToolContext(_RealToolContext):  # type: ignore[misc,no-redef]
        """ToolContext compatible with both real ADK runtime and test mocking."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            mock_fields = {"state", "auth_response", "actions", "user_id"}
            if any(k in kwargs for k in mock_fields) and not args:
                self._mock_state = kwargs.get("state") or {}
                self._mock_auth_response = kwargs.get("auth_response") or {}
                self._mock_user_id = kwargs.get("user_id")
                self._mock_actions = kwargs.get("actions")
            else:
                super().__init__(*args, **kwargs)

        @property
        def state(self) -> dict[str, Any]:
            if hasattr(self, "_mock_state"):
                return self._mock_state
            return super().state

        @property
        def auth_response(self) -> dict[str, Any]:
            if hasattr(self, "_mock_auth_response"):
                return self._mock_auth_response
            return getattr(self, "_auth_response", {})

        @property
        def user_id(self) -> str:
            if hasattr(self, "_mock_user_id") and self._mock_user_id:
                return self._mock_user_id
            try:
                return super().user_id
            except Exception:
                return ""

except ImportError:
    ADK_AVAILABLE = False

    @dataclass
    class ToolContext:  # type: ignore[no-redef]
        """Fallback ToolContext matching `google.adk.tools.tool_context.ToolContext`."""

        state: dict[str, Any] = field(default_factory=dict)
        auth_response: dict[str, Any] = field(default_factory=dict)
        actions: Any = None
        user_id: str = ""

    @dataclass
    class LlmAgent:  # type: ignore[no-redef]
        """Fallback LlmAgent matching `google.adk.agents.LlmAgent`."""

        name: str
        model: str
        description: str = ""
        instruction: str = ""
        tools: list[Callable[..., Any]] = field(default_factory=list)
        sub_agents: list[LlmAgent] = field(default_factory=list)
        output_key: str | None = None
        mode: str = "chat"
        output_schema: Any = None
