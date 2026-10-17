import { describe, it, expect, vi } from 'vitest';
import '@testing-library/jest-dom';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { RequestQuotaModal } from '../RequestQuotaModal';
import { SelfServiceCard } from '../SelfServiceCard';
import { RequestsTab } from '../RequestsTab';
import { AuthMeResponse, QuotaGroup, QuotaRequest, User } from '../../types';

describe('Developer Self-Service & Quota Requests Components', () => {
  const mockUser: User = {
    email: 'developer@example.com',
    group_id: 'developers',
    status: 'ACTIVE',
    is_exempt: false,
    has_custom_quota: false,
    custom_quota_usd: null,
    custom_overage_usd: null,
    is_temporary_quota: false,
    current_week: {
      week_id: '2026-W41',
      total_tokens: 15000000,
      total_requests: 45,
      gross_spend_usd: 42.5,
      quota_credits_usd: 50.0,
      remaining_credit_usd: 7.5,
      net_billable_cost_usd: 0.0,
      overage_buffer_usd: 10.0,
      spend_breakdown: { input_spend_usd: 25.0, output_spend_usd: 15.0, cached_spend_usd: 2.5 },
      tokens_by_model: {
        'gemini-1.5-pro': 10000000,
        'gemini-1.5-flash': 5000000,
      },
      spend_by_model: {
        'gemini-1.5-pro': 35.0,
        'gemini-1.5-flash': 7.5,
      },
      credit_utilization_percentage: 85.0,
      last_active: '2026-10-12T12:00:00Z',
    },
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-12T12:00:00Z',
  };

  const mockGroup: QuotaGroup = {
    group_id: 'developers',
    display_name: 'Developers Group',
    description: 'Engineering devs',
    weekly_quota_usd: 50.0,
    overage_buffer_usd: 10.0,
    is_exempt: false,
  };

  const mockAuthMe: AuthMeResponse = {
    email: 'developer@example.com',
    is_admin: false,
    user: mockUser,
    group: mockGroup,
    credit_pool: {
      tier_key: 'plus',
      tier_name: 'Gemini Enterprise Plus',
      usage_wtu: 12000000,
      limit_wtu: 37500000,
      usage_usd: 42.5,
      limit_usd: 75.0,
      utilization_pct: 56.6,
      next_reset_utc: new Date(Date.now() + 86400000 * 3).toISOString(),
    },
    active_request: null,
    in_cooldown: false,
    cooldown_until: null,
    admin_note: null,
    warning_threshold_reached: true,
  };

  const mockRequests: QuotaRequest[] = [
    {
      request_id: 'req-001',
      user_email: 'developer@example.com',
      current_group_id: 'developers',
      current_quota_usd: 50.0,
      current_spend_usd: 42.5,
      requested_quota_usd: 75.0,
      reason_category: 'SPRINT_DEADLINE',
      justification: 'Critical sprint deadline delivery for payments',
      duration_needed: 'TEMPORARY_WEEKLY',
      status: 'PENDING',
      created_at: '2026-10-12T10:00:00Z',
      reviewed_by: null,
      reviewed_at: null,
      admin_note: null,
    },
    {
      request_id: 'req-002',
      user_email: 'other@example.com',
      current_group_id: 'business-users',
      current_quota_usd: 10.0,
      current_spend_usd: 12.0,
      requested_quota_usd: 25.0,
      reason_category: 'REFACTORING',
      justification: 'Codebase cleanup',
      duration_needed: 'PERMANENT',
      status: 'APPROVED',
      created_at: '2026-10-11T10:00:00Z',
      reviewed_by: 'admin@example.com',
      reviewed_at: '2026-10-11T12:00:00Z',
      admin_note: 'Approved for Q4 refactoring sprint',
    },
  ];

  describe('RequestQuotaModal', () => {
    it('renders modal with current allowance and category options', () => {
      render(
        <RequestQuotaModal
          open={true}
          onClose={vi.fn()}
          onSubmit={vi.fn()}
          user={mockUser}
          group={mockGroup}
        />
      );

      expect(screen.getByText('Request Quota Increase')).toBeInTheDocument();
      expect(screen.getByText('Allowance: $50.00/wk')).toBeInTheDocument();
      expect(screen.getByText('+$25 ($75)')).toBeInTheDocument();
      expect(screen.getByText('+$50 ($100)')).toBeInTheDocument();
    });

    it('submits valid payload when form is filled', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined);
      render(
        <RequestQuotaModal
          open={true}
          onClose={vi.fn()}
          onSubmit={onSubmit}
          user={mockUser}
          group={mockGroup}
        />
      );

      // Enter justification
      const input = screen.getByPlaceholderText(/e\.g\. Critical sprint deadline/i);
      fireEvent.change(input, { target: { value: 'Refactoring large codebase for Q4 release' } });

      // Click submit
      const submitBtn = screen.getByRole('button', { name: /Submit Request/i });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith({
          requested_quota_usd: 75,
          reason_category: 'SPRINT_DEADLINE',
          justification: 'Refactoring large codebase for Q4 release',
          duration_needed: 'TEMPORARY_WEEKLY',
        });
      });
    });
  });

  describe('SelfServiceCard', () => {
    it('renders developer email, warning badge for 80%+ spend, and spend metrics', () => {
      render(
        <SelfServiceCard
          authMe={mockAuthMe}
          onOpenRequestModal={vi.fn()}
          onCancelRequest={vi.fn()}
        />
      );

      expect(screen.getByText('developer@example.com')).toBeInTheDocument();
      expect(screen.getByText(/WARNING \(80\%\+ Used\)/i)).toBeInTheDocument();
      expect(screen.getByText('$42.50')).toBeInTheDocument();
      expect(screen.getByText(/Developers Group/i)).toBeInTheDocument();
    });

    it('renders active request banner and triggers cancel action', async () => {
      const onCancel = vi.fn().mockResolvedValue(undefined);
      const authWithPending: AuthMeResponse = {
        ...mockAuthMe,
        active_request: mockRequests[0],
      };

      render(
        <SelfServiceCard
          authMe={authWithPending}
          onOpenRequestModal={vi.fn()}
          onCancelRequest={onCancel}
        />
      );

      expect(screen.getByText(/Quota Increase Pending: Requested \$75.00\/wk/i)).toBeInTheDocument();
      const cancelBtn = screen.getByRole('button', { name: /Cancel Request/i });
      fireEvent.click(cancelBtn);
      await waitFor(() => {
        expect(onCancel).toHaveBeenCalledWith('req-001');
      });
    });

    it('renders cooldown banner when in_cooldown is true', () => {
      const authCooldown: AuthMeResponse = {
        ...mockAuthMe,
        in_cooldown: true,
        admin_note: 'Capacity full this week',
      };

      render(
        <SelfServiceCard
          authMe={authCooldown}
          onOpenRequestModal={vi.fn()}
          onCancelRequest={vi.fn()}
        />
      );

      expect(screen.getByText(/Cooldown Active: Previous request declined/i)).toBeInTheDocument();
      expect(screen.getByText(/Capacity full this week/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Cooldown Active/i })).toBeDisabled();
    });
  });

  describe('RequestsTab', () => {
    it('renders request list with pending badge and status chips', () => {
      render(<RequestsTab requests={mockRequests} onRefresh={vi.fn()} />);

      expect(screen.getByText(/Quota Increase Requests/i)).toBeInTheDocument();
      expect(screen.getByText(/1 pending/i)).toBeInTheDocument();
      expect(screen.getByText('developer@example.com')).toBeInTheDocument();
      expect(screen.getByText('$75.00/wk')).toBeInTheDocument();
    });

    it('opens approval dialog when Approve is clicked', () => {
      render(<RequestsTab requests={mockRequests} onRefresh={vi.fn()} />);

      const approveBtns = screen.getAllByRole('button', { name: /Approve/i });
      fireEvent.click(approveBtns[0]);

      expect(screen.getByText('Approve Quota Increase Request')).toBeInTheDocument();
      expect(screen.getByLabelText(/Approved Weekly Quota/i)).toBeInTheDocument();
      expect(screen.getByText(/Temporary — Current Week Only/i)).toBeInTheDocument();
    });

    it('opens rejection dialog when Reject is clicked', () => {
      render(<RequestsTab requests={mockRequests} onRefresh={vi.fn()} />);

      const rejectBtn = screen.getByRole('button', { name: /Reject/i });
      fireEvent.click(rejectBtn);

      expect(screen.getByText('Decline Quota Increase Request')).toBeInTheDocument();
      expect(screen.getByLabelText(/Decline Reason \/ Admin Note/i)).toBeInTheDocument();
    });
  });
});
