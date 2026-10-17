# Antigravity Quota Concierge Agent Guidelines & Standards

When developing, refactoring, or adding capabilities to the `antigravity_quota_concierge` agent or any ADK agents in this repository, strictly adhere to the following architectural standards:

## 1. State Management & Namespacing
- **User Scope (`user:*`)**: Store persistent user preferences and identity in the `user:` namespace:
  - `user:email`: Verified user email address
  - `user:preferred_option`: User's default or last selected quota package
  - `user:last_reason_category`: Last requested reason category
- **Session Scope / Transient**: Store in-flight workflow state (`active_request_id`, `current_quota_usd`) using session-scoped or plain keys.
- **Backward Compatibility**: Whenever modifying tool state readers or writers, maintain backward compatibility:
  - Read: Check `user:<key>` first, falling back to legacy `<key>`.
  - Write: Populate both `user:<key>` and `<key>` so existing caller contracts remain intact.

## 2. Schema-Driven State & Task Output
- Model all structured agent state and task completions with Pydantic (`schemas.py`).
- Use `validation_alias=AliasChoices("user:key", "key")` and `ConfigDict(populate_by_name=True)` to allow seamless validation of raw `tool_context.state` dictionaries.
- Avoid passing raw, unvalidated dicts between agents.

## 3. Subagent Task Delegation (ADK 2.0)
- Subagents that perform discrete transactional actions (such as `quota_request_agent`) MUST be configured with:
  - `mode="task"`
  - `output_schema=<PydanticModel>`
- The subagent system instruction MUST specify explicit task termination criteria and instruct the agent to produce the final structured payload upon completion.

## 4. Testability & Offline Compatibility
- All tools and agent definitions MUST remain runnable and testable via `_adk_compat.py`.
- Unit tests in `concierge-agent/tests/` MUST execute 100% offline without requiring `google-adk` to be installed.
- Do not introduce runtime dependencies that break zero-dependency testing.
