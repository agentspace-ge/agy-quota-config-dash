import React, { useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Grid,
  LinearProgress,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import BlockIcon from '@mui/icons-material/Block';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty';
import CancelOutlinedIcon from '@mui/icons-material/CancelOutlined';
import LightbulbOutlinedIcon from '@mui/icons-material/LightbulbOutlined';
import LayersOutlinedIcon from '@mui/icons-material/LayersOutlined';
import BoltOutlinedIcon from '@mui/icons-material/BoltOutlined';
import PsychologyOutlinedIcon from '@mui/icons-material/PsychologyOutlined';
import { AuthMeResponse } from '../types';

export interface SelfServiceCardProps {
  authMe: AuthMeResponse | null;
  onOpenRequestModal: () => void;
  onCancelRequest?: (requestId: string) => Promise<void>;
  loading?: boolean;
}

export const SelfServiceCard: React.FC<SelfServiceCardProps> = ({
  authMe,
  onOpenRequestModal,
  onCancelRequest,
  loading = false,
}) => {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState('');

  if (loading || !authMe) {
    return (
      <Card sx={{ p: 4, textAlign: 'center', borderRadius: 3 }}>
        <CircularProgress size={32} sx={{ mb: 2 }} />
        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
          Loading your developer quota profile...
        </Typography>
      </Card>
    );
  }

  const {
    email,
    is_admin,
    user,
    group,
    credit_pool,
    active_request,
    in_cooldown,
    cooldown_until,
    admin_note,
    warning_threshold_reached,
  } = authMe;

  const effectiveQuota =
    user.has_custom_quota && user.custom_quota_usd != null
      ? user.custom_quota_usd
      : (group?.weekly_quota_usd ?? 50.0);

  const effectiveBuffer =
    user.has_custom_quota && user.custom_overage_usd != null
      ? user.custom_overage_usd
      : (group?.overage_buffer_usd ?? 10.0);

  const currentSpend = user.current_week?.gross_spend_usd ?? 0.0;
  const remainingCredit = Math.max(0, effectiveQuota - currentSpend);
  const utilizationPct =
    effectiveQuota > 0 ? (currentSpend / effectiveQuota) * 100 : 0;

  // Countdown formatter
  const formatCountdown = (targetDateStr: string | null | undefined): string => {
    if (!targetDateStr) return 'End of cycle';
    const target = new Date(targetDateStr).getTime();
    const now = Date.now();
    const diffMs = target - now;
    if (diffMs <= 0) return 'Resetting soon';

    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    const diffHours = Math.floor((diffMs % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const diffMins = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));

    if (diffDays > 0) {
      return `${diffDays}d ${diffHours}h`;
    }
    if (diffHours > 0) {
      return `${diffHours}h ${diffMins}m`;
    }
    return `${diffMins}m`;
  };

  const resetCountdown = formatCountdown(credit_pool?.next_reset_utc);
  const cooldownCountdown = formatCountdown(cooldown_until || credit_pool?.next_reset_utc);

  // Status Badge Logic
  const renderStatusBadge = () => {
    if (user.is_exempt) {
      return (
        <Chip
          size="medium"
          label="⚪ EXEMPT"
          sx={{
            fontWeight: 700,
            fontSize: '0.82rem',
            bgcolor: isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.08)',
            color: 'text.primary',
            border: '1px solid',
            borderColor: 'divider',
          }}
        />
      );
    }
    if (user.status === 'MANUALLY_DISABLED') {
      return (
        <Chip
          size="medium"
          icon={<BlockIcon sx={{ fontSize: '18px !important', color: '#ef4444 !important' }} />}
          label="🔴 MANUALLY LOCKED"
          sx={{
            fontWeight: 700,
            fontSize: '0.82rem',
            bgcolor: isDark ? 'rgba(239, 68, 68, 0.15)' : 'rgba(239, 68, 68, 0.12)',
            color: '#ef4444',
            border: '1px solid rgba(239, 68, 68, 0.3)',
          }}
        />
      );
    }
    if (user.status === 'AUTO_DISABLED') {
      return (
        <Tooltip title="Allowance exceeded. Paused in gatekeeper group until weekly reset or quota increase approval." arrow>
          <Chip
            size="medium"
            icon={<WarningAmberIcon sx={{ fontSize: '18px !important', color: '#f97316 !important' }} />}
            label="🟠 AUTO-THROTTLED"
            sx={{
              fontWeight: 700,
              fontSize: '0.82rem',
              bgcolor: isDark ? 'rgba(249, 115, 22, 0.15)' : 'rgba(249, 115, 22, 0.12)',
              color: '#f97316',
              border: '1px solid rgba(249, 115, 22, 0.3)',
            }}
          />
        </Tooltip>
      );
    }
    if (warning_threshold_reached || utilizationPct >= 80) {
      return (
        <Tooltip title="Pacing alert: You have reached 80%+ of your weekly quota. Request an increase before throttling occurs." arrow>
          <Chip
            size="medium"
            icon={<WarningAmberIcon sx={{ fontSize: '18px !important', color: '#f59e0b !important' }} />}
            label="🟡 WARNING (80%+ Used)"
            sx={{
              fontWeight: 700,
              fontSize: '0.82rem',
              bgcolor: isDark ? 'rgba(245, 158, 11, 0.15)' : 'rgba(245, 158, 11, 0.12)',
              color: '#f59e0b',
              border: '1px solid rgba(245, 158, 11, 0.3)',
            }}
          />
        </Tooltip>
      );
    }
    return (
      <Chip
        size="medium"
        icon={<CheckCircleOutlineIcon sx={{ fontSize: '18px !important', color: '#10b981 !important' }} />}
        label="🟢 ACTIVE"
        sx={{
          fontWeight: 700,
          fontSize: '0.82rem',
          bgcolor: isDark ? 'rgba(16, 185, 129, 0.15)' : 'rgba(16, 185, 129, 0.12)',
          color: '#10b981',
          border: '1px solid rgba(16, 185, 129, 0.3)',
        }}
      />
    );
  };

  // Progress Bar Color Logic: green <75%, yellow 75-99%, red >=100%
  const getProgressBarColor = () => {
    if (utilizationPct >= 100) return '#ef4444';
    if (utilizationPct >= 75) return '#f59e0b';
    return '#10b981';
  };

  // Handle Request Cancellation
  const handleCancelClick = async () => {
    if (!active_request || !onCancelRequest) return;
    setCancelling(true);
    setCancelError('');
    try {
      await onCancelRequest(active_request.request_id);
    } catch (err: any) {
      setCancelError(err.message || 'Failed to cancel quota request.');
    } finally {
      setCancelling(false);
    }
  };

  // Usage & Model Breakdown calculations
  const tokensByModel = user.current_week?.tokens_by_model || {};
  const spendByModel = user.current_week?.spend_by_model || {};
  const modelKeys = Array.from(new Set([...Object.keys(tokensByModel), ...Object.keys(spendByModel)]));

  let frontierSpend = 0;
  let lightweightSpend = 0;
  let totalModelSpend = 0;

  modelKeys.forEach((key) => {
    const s = spendByModel[key] || 0;
    totalModelSpend += s;
    const lower = key.toLowerCase();
    if (lower.includes('pro') || lower.includes('sonnet') || lower.includes('opus') || lower.includes('o1') || lower.includes('o3')) {
      frontierSpend += s;
    } else {
      lightweightSpend += s;
    }
  });

  const frontierPct = totalModelSpend > 0 ? (frontierSpend / totalModelSpend) * 100 : 0;
  const lightweightPct = totalModelSpend > 0 ? (lightweightSpend / totalModelSpend) * 100 : 0;

  const initials = email
    ? email
        .split('@')[0]
        .slice(0, 2)
        .toUpperCase()
    : 'DV';

  return (
    <Card
      sx={{
        borderRadius: 3,
        border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.1)' : '#e2e8f0'}`,
        backgroundColor: isDark ? '#111827' : '#ffffff',
        boxShadow: isDark ? '0 8px 32px rgba(0, 0, 0, 0.4)' : '0 4px 20px rgba(0, 0, 0, 0.05)',
        overflow: 'hidden',
        mb: 3,
      }}
    >
      <CardContent sx={{ p: { xs: 2.5, md: 3.5 } }}>
        {/* Top Header: Developer Identity & Live Status Badge */}
        <Box
          sx={{
            display: 'flex',
            flexDirection: { xs: 'column', sm: 'row' },
            justifyContent: 'space-between',
            alignItems: { xs: 'flex-start', sm: 'center' },
            gap: 2,
            mb: 3,
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Avatar
              sx={{
                width: 52,
                height: 52,
                bgcolor: 'primary.main',
                fontSize: '1.2rem',
                fontWeight: 700,
                boxShadow: isDark ? '0 0 16px rgba(99, 102, 241, 0.4)' : '0 2px 8px rgba(99, 102, 241, 0.25)',
              }}
            >
              {initials}
            </Avatar>
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, flexWrap: 'wrap' }}>
                <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.2rem', letterSpacing: '-0.01em' }}>
                  {email}
                </Typography>
                {is_admin && (
                  <Chip
                    label="ADMIN"
                    size="small"
                    sx={{
                      height: 20,
                      fontSize: '0.68rem',
                      fontWeight: 700,
                      bgcolor: isDark ? 'rgba(99, 102, 241, 0.2)' : 'rgba(99, 102, 241, 0.12)',
                      color: 'primary.light',
                      border: '1px solid rgba(99, 102, 241, 0.3)',
                    }}
                  />
                )}
                {user.is_temporary_quota && (
                  <Chip
                    label="TEMPORARY QUOTA"
                    size="small"
                    sx={{
                      height: 20,
                      fontSize: '0.68rem',
                      fontWeight: 700,
                      bgcolor: isDark ? 'rgba(245, 158, 11, 0.2)' : 'rgba(245, 158, 11, 0.12)',
                      color: '#f59e0b',
                      border: '1px solid rgba(245, 158, 11, 0.3)',
                    }}
                  />
                )}
              </Box>
              <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mt: 0.25 }}>
                Personal Developer Quota & Cloud Identity Resource Allocation
              </Typography>
            </Box>
          </Box>

          <Box sx={{ alignSelf: { xs: 'flex-start', sm: 'center' } }}>
            {renderStatusBadge()}
          </Box>
        </Box>

        <Divider sx={{ mb: 3 }} />

        {/* Key Metrics Grid */}
        <Grid container spacing={2.5} sx={{ mb: 3 }}>
          {/* 1. Assigned Group & Allowance */}
          <Grid item xs={12} sm={6} md={3}>
            <Paper
              variant="outlined"
              sx={{
                p: 2,
                height: '100%',
                borderRadius: 2,
                bgcolor: isDark ? 'rgba(255, 255, 255, 0.02)' : '#f8fafc',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <Box>
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  ASSIGNED GROUP
                </Typography>
                <Typography variant="subtitle1" sx={{ fontWeight: 700, mt: 0.5, lineHeight: 1.25 }}>
                  {group?.display_name || user.group_id || 'Business Users'}
                </Typography>
              </Box>
              <Typography variant="caption" sx={{ color: 'text.secondary', mt: 1, display: 'block' }}>
                ${effectiveQuota.toFixed(2)}/wk allowance + ${effectiveBuffer.toFixed(2)} buffer
              </Typography>
            </Paper>
          </Grid>

          {/* 2. Spend This Week */}
          <Grid item xs={12} sm={6} md={3}>
            <Paper
              variant="outlined"
              sx={{
                p: 2,
                height: '100%',
                borderRadius: 2,
                bgcolor: isDark ? 'rgba(255, 255, 255, 0.02)' : '#f8fafc',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <Box>
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  SPEND THIS WEEK
                </Typography>
                <Typography
                  variant="h5"
                  sx={{
                    fontWeight: 700,
                    mt: 0.5,
                    fontVariantNumeric: 'tabular-nums',
                    color: currentSpend >= effectiveQuota ? 'error.main' : 'text.primary',
                  }}
                >
                  ${currentSpend.toFixed(2)}
                </Typography>
              </Box>
              <Typography variant="caption" sx={{ color: remainingCredit > 0 ? 'secondary.main' : 'error.main', mt: 1, display: 'block', fontWeight: 600 }}>
                {remainingCredit > 0 ? `$${remainingCredit.toFixed(2)} credits remaining` : `Exceeded by $${(currentSpend - effectiveQuota).toFixed(2)}`}
              </Typography>
            </Paper>
          </Grid>

          {/* 3. Credit Utilization Progress */}
          <Grid item xs={12} sm={6} md={3}>
            <Paper
              variant="outlined"
              sx={{
                p: 2,
                height: '100%',
                borderRadius: 2,
                bgcolor: isDark ? 'rgba(255, 255, 255, 0.02)' : '#f8fafc',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
                  <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    QUOTA UTILIZATION
                  </Typography>
                  <Typography variant="caption" sx={{ fontWeight: 700, color: getProgressBarColor() }}>
                    {utilizationPct.toFixed(1)}%
                  </Typography>
                </Box>
                <LinearProgress
                  variant="determinate"
                  value={Math.min(100, utilizationPct)}
                  sx={{
                    my: 1.25,
                    height: 8,
                    borderRadius: 4,
                    bgcolor: isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0',
                    '& .MuiLinearProgress-bar': {
                      borderRadius: 4,
                      bgcolor: getProgressBarColor(),
                    },
                  }}
                />
              </Box>
              <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                Pacing: {utilizationPct < 75 ? 'Optimal' : utilizationPct < 100 ? 'Approaching Limit' : 'Throttled'}
              </Typography>
            </Paper>
          </Grid>

          {/* 4. Countdown to Auto-Reset */}
          <Grid item xs={12} sm={6} md={3}>
            <Paper
              variant="outlined"
              sx={{
                p: 2,
                height: '100%',
                borderRadius: 2,
                bgcolor: isDark ? 'rgba(255, 255, 255, 0.02)' : '#f8fafc',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <Box>
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  WEEKLY RESET
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5 }}>
                  <AccessTimeIcon sx={{ fontSize: 20, color: 'primary.light' }} />
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                    {resetCountdown}
                  </Typography>
                </Box>
              </Box>
              <Typography variant="caption" sx={{ color: 'text.secondary', mt: 1, display: 'block' }}>
                Cloud Monitoring auto-reverts weekly
              </Typography>
            </Paper>
          </Grid>
        </Grid>

        {/* Dynamic Request Action & Status Banner */}
        {cancelError && (
          <Alert severity="error" sx={{ mb: 2.5, borderRadius: 2 }} onClose={() => setCancelError('')}>
            {cancelError}
          </Alert>
        )}

        {/* Case 1: Active Pending Request */}
        {active_request && active_request.status === 'PENDING' ? (
          <Paper
            sx={{
              p: 2.5,
              mb: 3,
              borderRadius: 2.5,
              bgcolor: isDark ? 'rgba(245, 158, 11, 0.12)' : 'rgba(245, 158, 11, 0.08)',
              border: '1px solid',
              borderColor: isDark ? 'rgba(245, 158, 11, 0.35)' : 'rgba(245, 158, 11, 0.3)',
              display: 'flex',
              flexDirection: { xs: 'column', sm: 'row' },
              justifyContent: 'space-between',
              alignItems: { xs: 'flex-start', sm: 'center' },
              gap: 2,
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.75 }}>
              <HourglassEmptyIcon sx={{ color: '#f59e0b', fontSize: 28, mt: 0.25 }} />
              <Box>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, color: isDark ? '#fbbf24' : '#d97706' }}>
                  ⏳ Quota Increase Pending: Requested ${active_request.requested_quota_usd.toFixed(2)}/wk · Awaiting Admin Review
                </Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mt: 0.5 }}>
                  Submitted {new Date(active_request.created_at).toLocaleString()} · Category: <strong>{active_request.reason_category}</strong> · Duration:{' '}
                  <strong>{active_request.duration_needed === 'TEMPORARY_WEEKLY' ? 'This week only' : 'Permanent'}</strong>
                </Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', fontStyle: 'italic', mt: 0.25 }}>
                  "{active_request.justification}"
                </Typography>
              </Box>
            </Box>

            {onCancelRequest && (
              <Button
                variant="outlined"
                color="warning"
                size="small"
                startIcon={cancelling ? <CircularProgress size={14} color="inherit" /> : <CancelOutlinedIcon fontSize="small" />}
                onClick={handleCancelClick}
                disabled={cancelling}
                sx={{
                  flexShrink: 0,
                  fontWeight: 600,
                  borderRadius: 2,
                }}
              >
                {cancelling ? 'Cancelling...' : 'Cancel Request'}
              </Button>
            )}
          </Paper>
        ) : in_cooldown ? (
          /* Case 2: Cooldown Active (Previous Request Rejected) */
          <Paper
            sx={{
              p: 2.5,
              mb: 3,
              borderRadius: 2.5,
              bgcolor: isDark ? 'rgba(239, 68, 68, 0.08)' : 'rgba(239, 68, 68, 0.05)',
              border: '1px solid',
              borderColor: isDark ? 'rgba(239, 68, 68, 0.25)' : 'rgba(239, 68, 68, 0.2)',
              display: 'flex',
              flexDirection: { xs: 'column', sm: 'row' },
              justifyContent: 'space-between',
              alignItems: { xs: 'flex-start', sm: 'center' },
              gap: 2,
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.75 }}>
              <BlockIcon sx={{ color: '#ef4444', fontSize: 28, mt: 0.25 }} />
              <Box>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#ef4444' }}>
                  🚫 Cooldown Active: Previous request declined
                </Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
                  {admin_note ? (
                    <span>
                      Admin Note: <em>« {admin_note} »</em>
                    </span>
                  ) : (
                    'Your previous quota request was reviewed and closed by an administrator.'
                  )}
                </Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mt: 0.5 }}>
                  You may submit a new request after weekly reset in <strong>{cooldownCountdown}</strong>.
                </Typography>
              </Box>
            </Box>

            <Button
              variant="outlined"
              disabled
              size="small"
              sx={{
                flexShrink: 0,
                borderRadius: 2,
                fontWeight: 600,
              }}
            >
              Cooldown Active
            </Button>
          </Paper>
        ) : (
          /* Case 3: Standard Request Action */
          <Box
            sx={{
              display: 'flex',
              flexDirection: { xs: 'column', sm: 'row' },
              justifyContent: 'space-between',
              alignItems: { xs: 'flex-start', sm: 'center' },
              p: 2.5,
              mb: 3,
              borderRadius: 2.5,
              bgcolor: isDark ? 'rgba(99, 102, 241, 0.06)' : 'rgba(99, 102, 241, 0.04)',
              border: '1px solid',
              borderColor: isDark ? 'rgba(99, 102, 241, 0.2)' : 'rgba(99, 102, 241, 0.15)',
              gap: 2,
            }}
          >
            <Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 700, color: 'text.primary' }}>
                Need More Developer Allowance?
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mt: 0.5 }}>
                {warning_threshold_reached || utilizationPct >= 80
                  ? '⚡ You have reached 80%+ spend. Request an increase now to prevent automatic development throttling.'
                  : 'Submit a sprint boost or permanent tier upgrade for fast administrative review.'}
              </Typography>
            </Box>

            <Button
              variant="contained"
              startIcon={<TrendingUpIcon />}
              onClick={onOpenRequestModal}
              disabled={user.is_exempt || user.status === 'MANUALLY_DISABLED'}
              sx={{
                flexShrink: 0,
                fontWeight: 600,
                px: 2.5,
                py: 1,
                borderRadius: 2,
              }}
            >
              Request Quota Increase
            </Button>
          </Box>
        )}

        {/* Collapsible Accordion: Usage & Model Efficiency Breakdown */}
        <Accordion
          defaultExpanded={false}
          elevation={0}
          sx={{
            borderRadius: '12px !important',
            border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
            bgcolor: isDark ? 'rgba(255, 255, 255, 0.02)' : '#f8fafc',
            '&:before': { display: 'none' },
          }}
        >
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
              <LayersOutlinedIcon sx={{ color: 'primary.main', fontSize: 20 }} />
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                Usage & Model Efficiency Breakdown
              </Typography>
              <Chip
                label={`${modelKeys.length} models active`}
                size="small"
                sx={{ height: 20, fontSize: '0.7rem', fontWeight: 600 }}
              />
            </Box>
          </AccordionSummary>

          <AccordionDetails sx={{ pt: 0, pb: 2.5 }}>
            {/* Efficiency Tip Card */}
            <Paper
              sx={{
                p: 2,
                mb: 2.5,
                borderRadius: 2,
                bgcolor: isDark ? 'rgba(16, 185, 129, 0.08)' : 'rgba(16, 185, 129, 0.06)',
                border: '1px solid',
                borderColor: isDark ? 'rgba(16, 185, 129, 0.25)' : 'rgba(16, 185, 129, 0.2)',
                display: 'flex',
                alignItems: 'flex-start',
                gap: 1.5,
              }}
            >
              <LightbulbOutlinedIcon sx={{ color: '#10b981', fontSize: 22, mt: 0.25 }} />
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 600, color: isDark ? '#34d399' : '#059669' }}>
                  {frontierPct > 0
                    ? `💡 Pro / Reasoning models accounted for ${frontierPct.toFixed(0)}% of your spend. Switching to Flash models for routine edits yields up to 4x higher token efficiency.`
                    : '💡 Excellent model pacing! You are utilizing high-efficiency lightweight models to maximize your weekly token budget.'}
                </Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mt: 0.5 }}>
                  Configure your Antigravity agent or editor rules to default to Gemini 2.0 Flash for code search, file analysis, and unit test generation.
                </Typography>
              </Box>
            </Paper>

            {/* Frontier vs Fast Model Ratios */}
            <Grid container spacing={2} sx={{ mb: 2.5 }}>
              <Grid item xs={12} sm={6}>
                <Paper
                  variant="outlined"
                  sx={{
                    p: 2,
                    borderRadius: 2,
                    bgcolor: isDark ? 'rgba(255, 255, 255, 0.02)' : '#ffffff',
                  }}
                >
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <PsychologyOutlinedIcon sx={{ color: '#6366f1', fontSize: 20 }} />
                      <Typography variant="caption" sx={{ fontWeight: 700, textTransform: 'uppercase' }}>
                        Frontier / Reasoning Models
                      </Typography>
                    </Box>
                    <Typography variant="caption" sx={{ fontWeight: 700, color: '#6366f1' }}>
                      {frontierPct.toFixed(1)}%
                    </Typography>
                  </Box>
                  <Typography variant="h6" sx={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                    ${frontierSpend.toFixed(2)}
                  </Typography>
                  <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                    Gemini 1.5 Pro, Gemini 3 Pro, Claude Sonnet
                  </Typography>
                </Paper>
              </Grid>

              <Grid item xs={12} sm={6}>
                <Paper
                  variant="outlined"
                  sx={{
                    p: 2,
                    borderRadius: 2,
                    bgcolor: isDark ? 'rgba(255, 255, 255, 0.02)' : '#ffffff',
                  }}
                >
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <BoltOutlinedIcon sx={{ color: '#10b981', fontSize: 20 }} />
                      <Typography variant="caption" sx={{ fontWeight: 700, textTransform: 'uppercase' }}>
                        Fast / Lightweight Models
                      </Typography>
                    </Box>
                    <Typography variant="caption" sx={{ fontWeight: 700, color: '#10b981' }}>
                      {lightweightPct.toFixed(1)}%
                    </Typography>
                  </Box>
                  <Typography variant="h6" sx={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                    ${lightweightSpend.toFixed(2)}
                  </Typography>
                  <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                    Gemini 1.5 Flash, Gemini 2.0 Flash, Claude Haiku
                  </Typography>
                </Paper>
              </Grid>
            </Grid>

            {/* Model Breakdown Table */}
            {modelKeys.length > 0 ? (
              <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: 2 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Model Name</TableCell>
                      <TableCell align="right">Tokens</TableCell>
                      <TableCell align="right">Gross Spend</TableCell>
                      <TableCell align="right">Share</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {modelKeys.map((modelKey) => {
                      const tokens = tokensByModel[modelKey] || 0;
                      const spend = spendByModel[modelKey] || 0;
                      const sharePct = totalModelSpend > 0 ? (spend / totalModelSpend) * 100 : 0;
                      return (
                        <TableRow key={modelKey}>
                          <TableCell sx={{ fontFamily: 'monospace', fontWeight: 600 }}>{modelKey}</TableCell>
                          <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                            {tokens.toLocaleString()}
                          </TableCell>
                          <TableCell align="right" sx={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                            ${spend.toFixed(2)}
                          </TableCell>
                          <TableCell align="right">
                            <Chip
                              size="small"
                              label={`${sharePct.toFixed(1)}%`}
                              sx={{
                                height: 20,
                                fontSize: '0.68rem',
                                fontWeight: 600,
                              }}
                            />
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : (
              <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', textAlign: 'center', py: 2 }}>
                No model telemetry recorded yet for the current billing cycle.
              </Typography>
            )}
          </AccordionDetails>
        </Accordion>
      </CardContent>
    </Card>
  );
};
