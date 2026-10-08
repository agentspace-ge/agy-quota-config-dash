import React from 'react';
import { Box, Card, CardContent, Grid, LinearProgress, Typography, useTheme } from '@mui/material';
import PeopleAltOutlinedIcon from '@mui/icons-material/PeopleAltOutlined';
import BlockOutlinedIcon from '@mui/icons-material/BlockOutlined';
import TokenOutlinedIcon from '@mui/icons-material/TokenOutlined';
import AttachMoneyOutlinedIcon from '@mui/icons-material/AttachMoneyOutlined';
import AccountBalanceWalletOutlinedIcon from '@mui/icons-material/AccountBalanceWalletOutlined';
import WarningAmberOutlinedIcon from '@mui/icons-material/WarningAmberOutlined';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import { KPIStats } from '../types';

interface KPISummaryProps {
  kpis: KPIStats | null;
  loading?: boolean;
}

export const KPISummary: React.FC<KPISummaryProps> = ({ kpis }) => {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';

  const formatTokens = (tokens: number) => {
    if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(2)}M`;
    if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(1)}k`;
    return tokens.toLocaleString();
  };

  const poolUtilization = kpis && kpis.total_credits_allocated_usd > 0
    ? Math.min(100, (kpis.total_gross_usage_usd / kpis.total_credits_allocated_usd) * 100)
    : 0;

  const cards = [
    {
      title: 'Active Developers',
      value: kpis ? kpis.active_developers : '-',
      subtext: `${kpis?.exempt_developers || 0} exempt from limits`,
      icon: <PeopleAltOutlinedIcon sx={{ color: '#10b981', fontSize: 18 }} />,
      bgColor: isDark ? 'rgba(16, 185, 129, 0.12)' : 'rgba(16, 185, 129, 0.1)',
      borderColor: isDark ? 'rgba(16, 185, 129, 0.25)' : 'rgba(16, 185, 129, 0.3)',
      color: '#10b981',
    },
    {
      title: 'Auto-Throttled',
      value: kpis ? kpis.auto_throttled_developers : '-',
      subtext: `${kpis?.manually_locked_developers || 0} manually locked`,
      icon: <BlockOutlinedIcon sx={{ color: '#ef4444', fontSize: 18 }} />,
      bgColor: isDark ? 'rgba(239, 68, 68, 0.12)' : 'rgba(239, 68, 68, 0.1)',
      borderColor: isDark ? 'rgba(239, 68, 68, 0.25)' : 'rgba(239, 68, 68, 0.3)',
      color: '#ef4444',
    },
    {
      title: 'Tokens This Week',
      value: kpis ? formatTokens(kpis.total_tokens_this_week) : '-',
      subtext: kpis?.week_id ? `Week ${kpis.week_id}` : 'Current billing window',
      icon: <TokenOutlinedIcon sx={{ color: '#6366f1', fontSize: 18 }} />,
      bgColor: isDark ? 'rgba(99, 102, 241, 0.12)' : 'rgba(99, 102, 241, 0.1)',
      borderColor: isDark ? 'rgba(99, 102, 241, 0.25)' : 'rgba(99, 102, 241, 0.3)',
      color: '#6366f1',
    },
    {
      title: 'Gross Usage',
      value: kpis ? `$${kpis.total_gross_usage_usd.toFixed(2)}` : '-',
      subtext: 'Calculated token value',
      icon: <AttachMoneyOutlinedIcon sx={{ color: '#f59e0b', fontSize: 18 }} />,
      bgColor: isDark ? 'rgba(245, 158, 11, 0.12)' : 'rgba(245, 158, 11, 0.1)',
      borderColor: isDark ? 'rgba(245, 158, 11, 0.25)' : 'rgba(245, 158, 11, 0.3)',
      color: '#f59e0b',
    },
    {
      title: 'Credits Allocated',
      value: kpis ? `$${kpis.total_credits_allocated_usd.toFixed(2)}` : '-',
      subtext: 'Total organization pool',
      icon: <AccountBalanceWalletOutlinedIcon sx={{ color: '#3b82f6', fontSize: 18 }} />,
      bgColor: isDark ? 'rgba(59, 130, 246, 0.12)' : 'rgba(59, 130, 246, 0.1)',
      borderColor: isDark ? 'rgba(59, 130, 246, 0.25)' : 'rgba(59, 130, 246, 0.3)',
      color: '#3b82f6',
    },
    {
      title: 'Net Overages',
      value: kpis ? `$${kpis.total_net_overages_usd.toFixed(2)}` : '-',
      subtext: 'Spend above granted quota',
      icon: <WarningAmberOutlinedIcon sx={{ color: '#ef4444', fontSize: 18 }} />,
      bgColor: isDark ? 'rgba(239, 68, 68, 0.12)' : 'rgba(239, 68, 68, 0.1)',
      borderColor: isDark ? 'rgba(239, 68, 68, 0.25)' : 'rgba(239, 68, 68, 0.3)',
      color: '#ef4444',
    },
  ];

  return (
    <Box sx={{ mb: 3 }}>
      {/* 6 Top FinOps Metric Cards */}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {cards.map((card, idx) => (
          <Grid item xs={12} sm={6} md={2} key={idx}>
            <Card
              elevation={0}
              sx={{
                p: 0,
                height: '100%',
                backgroundColor: isDark ? '#111827' : '#ffffff',
                border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
                borderRadius: '12px',
                position: 'relative',
                overflow: 'hidden',
                transition: 'transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease',
                '&:hover': {
                  borderColor: card.borderColor,
                  transform: 'translateY(-2px)',
                  boxShadow: isDark
                    ? `0 4px 20px -4px ${card.bgColor}`
                    : '0 4px 12px rgba(0, 0, 0, 0.05)',
                },
              }}
            >
              <CardContent sx={{ p: '16px !important' }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
                  <Typography
                    variant="caption"
                    sx={{
                      color: isDark ? '#9ca3af' : '#64748b',
                      fontWeight: 600,
                      textTransform: 'uppercase',
                      letterSpacing: '0.06em',
                      fontSize: '0.7rem',
                    }}
                  >
                    {card.title}
                  </Typography>
                  <Box
                    sx={{
                      width: 28,
                      height: 28,
                      borderRadius: '8px',
                      backgroundColor: card.bgColor,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    {card.icon}
                  </Box>
                </Box>
                <Typography
                  variant="h5"
                  sx={{
                    fontWeight: 700,
                    letterSpacing: '-0.02em',
                    fontFamily: '"Inter", -apple-system, sans-serif',
                    fontVariantNumeric: 'tabular-nums',
                    color: isDark ? '#f9fafb' : '#0f172a',
                    fontSize: '1.45rem',
                  }}
                >
                  {card.value}
                </Typography>
                <Typography
                  variant="caption"
                  sx={{
                    color: isDark ? '#6b7280' : '#94a3b8',
                    mt: 0.5,
                    display: 'block',
                    fontSize: '0.75rem',
                  }}
                >
                  {card.subtext}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {/* Tenant Credit Pool Utilization Bar */}
      {kpis && kpis.total_credits_allocated_usd > 0 && (
        <Card
          elevation={0}
          sx={{
            p: 1.75,
            backgroundColor: isDark ? '#0f172a' : '#f8fafc',
            border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.06)' : '#e2e8f0'}`,
            borderRadius: '10px',
          }}
        >
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <TrendingUpIcon sx={{ fontSize: 16, color: '#6366f1' }} />
              <Typography variant="caption" sx={{ fontWeight: 600, color: isDark ? '#cbd5e1' : '#334155' }}>
                Tenant Organization Credit Pool Utilization
              </Typography>
            </Box>
            <Typography
              variant="caption"
              sx={{
                fontWeight: 600,
                fontFamily: 'monospace',
                color: poolUtilization > 80 ? '#f59e0b' : '#10b981',
              }}
            >
              ${kpis.total_gross_usage_usd.toFixed(2)} / ${kpis.total_credits_allocated_usd.toFixed(2)} ({poolUtilization.toFixed(1)}%)
            </Typography>
          </Box>
          <LinearProgress
            variant="determinate"
            value={poolUtilization}
            sx={{
              height: 6,
              borderRadius: 3,
              backgroundColor: isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0',
              '& .MuiLinearProgress-bar': {
                borderRadius: 3,
                background: poolUtilization > 90
                  ? 'linear-gradient(90deg, #f59e0b, #ef4444)'
                  : poolUtilization > 70
                  ? 'linear-gradient(90deg, #10b981, #f59e0b)'
                  : 'linear-gradient(90deg, #6366f1, #10b981)',
              },
            }}
          />
        </Card>
      )}
    </Box>
  );
};
