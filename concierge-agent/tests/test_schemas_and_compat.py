"""Tests for Pydantic schemas and ADK compat enhancements."""

import unittest
from pydantic import ValidationError

from antigravity_quota_concierge._adk_compat import LlmAgent
from antigravity_quota_concierge.schemas import QuotaRequestTaskOutput, ConciergeState


class TestSchemasAndCompat(unittest.TestCase):
    def test_quota_request_task_output_valid(self):
        output = QuotaRequestTaskOutput(
            request_id="req-12345",
            status="PENDING",
            requested_quota_usd=35.0,
            duration_needed="TEMPORARY_WEEKLY",
            reason_category="SPRINT_DEADLINE",
            confirmation_message="Submitted request req-12345 for $35.00/wk.",
        )
        self.assertEqual(output.request_id, "req-12345")
        self.assertEqual(output.requested_quota_usd, 35.0)

    def test_quota_request_task_output_validation_error(self):
        with self.assertRaises(ValidationError):
            QuotaRequestTaskOutput(
                request_id="req-12345",
                status="PENDING",
                requested_quota_usd="not-a-float",  # invalid
                duration_needed="TEMPORARY_WEEKLY",
                reason_category="SPRINT_DEADLINE",
                confirmation_message="msg",
            )

    def test_llm_agent_compat_supports_mode_and_output_schema(self):
        agent = LlmAgent(
            name="test_agent",
            model="gemini-3.5-flash",
            mode="task",
            output_schema=QuotaRequestTaskOutput,
        )
        self.assertEqual(agent.mode, "task")
        self.assertEqual(agent.output_schema, QuotaRequestTaskOutput)

    def test_concierge_state_validation_aliases(self):
        raw_state = {
            "user:email": "alex.morgan@example.com",
            "current_quota_usd": 6.0,
            "current_spend_usd": 6.04,
            "user:preferred_option": 2,
            "user:last_reason_category": "SPRINT_DEADLINE",
        }
        state = ConciergeState.model_validate(raw_state)
        self.assertEqual(state.user_email, "alex.morgan@example.com")
        self.assertEqual(state.preferred_option_number, 2)
        self.assertEqual(state.last_reason_category, "SPRINT_DEADLINE")
        self.assertEqual(state.current_quota_usd, 6.0)


if __name__ == "__main__":

    unittest.main()
