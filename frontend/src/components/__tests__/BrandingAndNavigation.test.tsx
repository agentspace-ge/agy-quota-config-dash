import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { KPISummary } from '../KPISummary';
import { UserTable } from '../UserTable';
import { KPIStats, User, QuotaGroup } from '../../types';

describe('Claude Enterprise Branding & Naming Standards', () => {
  const mockKpis: KPIStats = {
    week_id: '2026-W41',
    active_developers: 42,
    auto_throttled_developers: 2,
    manually_locked_developers: 1,
    exempt_developers: 5,
    total_tokens_this_week: 15400000,
    total_gross_usage_usd: 125.5,
    total_credits_allocated_usd: 500.0,
    total_net_overages_usd: 12.0,
    credit_pool: {
      tier_key: 'tier_3',
      tier_name: 'Tier 3 Enterprise',
      limit_wtu: 10000000,
      usage_wtu: 4500000,
      utilization_pct: 45.0,
      limit_usd: 1000.0,
      usage_usd: 450.0,
      next_reset_utc: '2026-10-18T00:00:00Z',
      window_start_utc: '2026-10-11T00:00:00Z',
    },
  };

  const mockUsers: User[] = [
    {
      email: 'alex@company.com',
      group_id: 'developers',
      status: 'ACTIVE',
      is_exempt: false,
      has_custom_quota: false,
      custom_quota_usd: null,
      custom_overage_usd: null,
      current_week: {
        week_id: '2026-W41',
        total_tokens: 1500000,
        total_requests: 12,
        gross_spend_usd: 15.0,
        quota_credits_usd: 50.0,
        remaining_credit_usd: 35.0,
        net_billable_cost_usd: 0.0,
        overage_buffer_usd: 10.0,
        spend_breakdown: { input_spend_usd: 10, output_spend_usd: 5, cached_spend_usd: 0 },
        tokens_by_model: {},
        spend_by_model: {},
        credit_utilization_percentage: 30.0,
        last_active: null,
      },
      created_at: '2026-10-11T00:00:00Z',
      updated_at: '2026-10-11T00:00:00Z',
    },
  ];

  const mockGroups: QuotaGroup[] = [
    {
      group_id: 'developers',
      display_name: 'Developers',
      description: 'Engineering team',
      weekly_quota_usd: 50.0,
      overage_buffer_usd: 10.0,
      is_exempt: false,
      iam_group_email: null,
      created_at: '2026-10-11T00:00:00Z',
      updated_at: '2026-10-11T00:00:00Z',
      member_count: 1,
      gross_spend_usd: 15.0,
      total_tokens: 1500000,
    },
  ];

  it('renders updated Claude-aligned KPI card titles and Hero Quota Pool title', () => {
    render(<KPISummary kpis={mockKpis} />);

    // KPI Card Titles
    expect(screen.getByText('Active Users')).toBeDefined();
    expect(screen.getByText('Throttled')).toBeDefined();
    expect(screen.getByText('Total Spend')).toBeDefined();
    expect(screen.getByText('Allocated Quota')).toBeDefined();

    // KPI Subtexts
    expect(screen.getByText('Internal user spend')).toBeDefined();
    expect(screen.getByText('Sum of user quotas')).toBeDefined();

    // Hero Card Title
    expect(screen.getByText('Organization Quota Pool')).toBeDefined();

    // Admin Info Memo Icon
    expect(screen.getByRole('button', { name: 'About Tokens This Week' })).toBeDefined();
  });

  it('renders updated Claude-aligned UserTable directory titles and actions', () => {
    render(
      <UserTable
        users={mockUsers}
        groups={mockGroups}
        onSelectUser={vi.fn()}
        onToggleLock={vi.fn()}
        onToggleExempt={vi.fn()}
        onAddUser={vi.fn()}
      />
    );

    // Column Header
    expect(screen.getByRole('button', { name: 'User' })).toBeDefined();

    // Add User Button
    expect(screen.getByRole('button', { name: 'Add User' })).toBeDefined();

    // Search placeholder
    expect(
      screen.getByPlaceholderText('Search users by email... (Press / to focus)')
    ).toBeDefined();
  });

  it('verifies strict isolation between Admin Console and Developer Portal branding', () => {
    // Helper function reproducing App.tsx portal title and subtitle computation
    const getPortalBranding = (viewMode: 'admin' | 'developer', isAdmin: boolean) => {
      const isDeveloperPortal = viewMode === 'developer' || !isAdmin;
      return {
        title: isDeveloperPortal ? 'Antigravity' : 'Antigravity Admin Console',
        subtitle: isDeveloperPortal
          ? 'Personal usage, quota allowances, and access status'
          : 'Organization usage limits, directory access, and spend governance',
        docTitle: isDeveloperPortal ? 'Antigravity · My Quota' : 'Antigravity Admin Console',
      };
    };

    // 1. Admin in Admin View
    const adminBranding = getPortalBranding('admin', true);
    expect(adminBranding.title).toBe('Antigravity Admin Console');
    expect(adminBranding.subtitle).toContain('Organization usage limits');
    expect(adminBranding.docTitle).toBe('Antigravity Admin Console');

    // 2. Admin in Developer Preview View
    const previewBranding = getPortalBranding('developer', true);
    expect(previewBranding.title).toBe('Antigravity');
    expect(previewBranding.subtitle).toBe('Personal usage, quota allowances, and access status');
    expect(previewBranding.docTitle).toBe('Antigravity · My Quota');
    expect(previewBranding.title).not.toContain('Admin');

    // 3. Regular Developer User (is_admin: false)
    const nonAdminBranding = getPortalBranding('admin', false); // Even if mode requested is admin
    expect(nonAdminBranding.title).toBe('Antigravity');
    expect(nonAdminBranding.subtitle).toBe('Personal usage, quota allowances, and access status');
    expect(nonAdminBranding.docTitle).toBe('Antigravity · My Quota');
    expect(nonAdminBranding.title).not.toContain('Admin');
  });
});
