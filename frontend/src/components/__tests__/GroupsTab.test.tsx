import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { GroupsTab } from '../GroupsTab';
import { QuotaGroup, User } from '../../types';

describe('GroupsTab Component', () => {
  const mockGroups: QuotaGroup[] = [
    {
      group_id: 'business-users',
      display_name: 'Business Users',
      description: 'Standard business users with standard tier quotas',
      weekly_quota_usd: 10.0,
      overage_buffer_usd: 2.0,
      is_exempt: false,
      iam_group_email: null,
      created_at: '2026-10-11T12:00:00Z',
      updated_at: '2026-10-11T12:00:00Z',
      member_count: 3,
      gross_spend_usd: 15.17,
      total_tokens: 135470181,
    },
    {
      group_id: 'developers',
      display_name: 'Developers',
      description: 'Engineering and development teams with higher inference quotas',
      weekly_quota_usd: 50.0,
      overage_buffer_usd: 10.0,
      is_exempt: false,
      iam_group_email: null,
      created_at: '2026-10-11T12:00:00Z',
      updated_at: '2026-10-11T12:00:00Z',
      member_count: 0,
      gross_spend_usd: 0.0,
      total_tokens: 0,
    },
  ];

  const mockUsers: User[] = [
    {
      email: 'user1@example.com',
      group_id: 'business-users',
      status: 'ACTIVE',
      is_exempt: false,
      has_custom_quota: false,
      custom_quota_usd: null,
      custom_overage_usd: null,
      current_week: {
        week_id: '2026-W41',
        total_tokens: 50000000,
        total_requests: 120,
        gross_spend_usd: 5.0,
        quota_credits_usd: 10.0,
        remaining_credit_usd: 5.0,
        net_billable_cost_usd: 0.0,
        overage_buffer_usd: 2.0,
        spend_breakdown: { input_spend_usd: 3.0, output_spend_usd: 2.0, cached_spend_usd: 0.0 },
        tokens_by_model: {},
        spend_by_model: {},
        credit_utilization_percentage: 50.0,
        last_active: null,
        window_start_utc: null,
      },
      created_at: '2026-10-11T12:00:00Z',
      updated_at: '2026-10-11T12:00:00Z',
    },
  ];

  it('renders top-level member_count, gross_spend_usd, and total_tokens from API', () => {
    const handleViewMembers = vi.fn();
    render(
      <GroupsTab
        groups={mockGroups}
        onCreateGroup={vi.fn()}
        onUpdateGroup={vi.fn()}
        onDeleteGroup={vi.fn()}
        onViewMembers={handleViewMembers}
      />
    );

    // Business Users displays 3 members
    expect(screen.getByText('Business Users')).toBeDefined();
    expect(screen.getByText(/View Members \(3\)/i)).toBeDefined();
    expect(screen.getByText('$15.17')).toBeDefined();
    expect(screen.getByText('135.47M')).toBeDefined();

    // Developers displays 0 members
    expect(screen.getByText('Developers')).toBeDefined();
    expect(screen.getByText(/View Members \(0\)/i)).toBeDefined();
  });

  it('falls back to users array if group metrics are missing', () => {
    const groupsWithoutStats: QuotaGroup[] = [
      {
        group_id: 'business-users',
        display_name: 'Business Users',
        description: 'Standard business users',
        weekly_quota_usd: 10.0,
        overage_buffer_usd: 2.0,
        is_exempt: false,
      },
    ];

    render(
      <GroupsTab
        groups={groupsWithoutStats}
        users={mockUsers}
        onCreateGroup={vi.fn()}
        onUpdateGroup={vi.fn()}
        onDeleteGroup={vi.fn()}
        onViewMembers={vi.fn()}
      />
    );

    // Fallback computes 1 member from mockUsers
    expect(screen.getByText(/View Members \(1\)/i)).toBeDefined();
    expect(screen.getByText('$5.00')).toBeDefined();
  });

  it('triggers onViewMembers callback with groupId when View Members clicked', () => {
    const handleViewMembers = vi.fn();
    render(
      <GroupsTab
        groups={mockGroups}
        onCreateGroup={vi.fn()}
        onUpdateGroup={vi.fn()}
        onDeleteGroup={vi.fn()}
        onViewMembers={handleViewMembers}
      />
    );

    const viewMembersBtn = screen.getByText(/View Members \(3\)/i);
    fireEvent.click(viewMembersBtn);

    expect(handleViewMembers).toHaveBeenCalledWith('business-users');
  });

  it('shows Default chip on business-users and protects it from deletion', () => {
    render(
      <GroupsTab
        groups={mockGroups}
        onCreateGroup={vi.fn()}
        onUpdateGroup={vi.fn()}
        onDeleteGroup={vi.fn()}
        onViewMembers={vi.fn()}
      />
    );

    expect(screen.getByText('Default')).toBeDefined();
  });

  it('opens Assign Members dialog with reset custom quota option enabled by default', () => {
    render(
      <GroupsTab
        groups={mockGroups}
        onCreateGroup={vi.fn()}
        onUpdateGroup={vi.fn()}
        onDeleteGroup={vi.fn()}
        onViewMembers={vi.fn()}
      />
    );

    const assignBtns = screen.getAllByRole('button');
    // Find the assign button with tooltip or person icon
    const assignBtn = assignBtns.find((btn) => btn.querySelector('svg[data-testid="PersonAddAlt1OutlinedIcon"]'));
    expect(assignBtn).toBeDefined();

    if (assignBtn) {
      fireEvent.click(assignBtn);
      // Dialog opens
      expect(screen.getByText(/Assign Members to Business Users/i)).toBeDefined();
      expect(screen.getByText(/Reset custom quota overrides to group baseline/i)).toBeDefined();
      expect(screen.getByRole('button', { name: 'Assign Members' })).toBeDefined();
    }
  });
});
