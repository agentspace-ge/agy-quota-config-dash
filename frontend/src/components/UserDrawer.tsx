import React, { useEffect, useState } from 'react';
import {
  Avatar,
  Box,
  Button,
  Chip,
  Divider,
  Drawer,
  FormControlLabel,
  Grid,
  IconButton,
  InputAdornment,
  MenuItem,
  Paper,
  Switch,
  TextField,
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import SaveIcon from '@mui/icons-material/Save';
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet';
import DonutLargeIcon from '@mui/icons-material/DonutLarge';
import TuneIcon from '@mui/icons-material/Tune';
import { AppConfig, QuotaGroup, User, UserUpdatePayload } from '../types';

interface UserDrawerProps {
  user: User | null;
  groups?: QuotaGroup[];
  config: AppConfig | null;
  nextResetUtc?: string | null;
  open: boolean;
  onClose: () => void;
  onSave: (email: string, payload: UserUpdatePayload) => Promise<void>;
}

const MODEL_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#3b82f6', '#ec4899', '#8b5cf6'];

export const UserDrawer: React.FC<UserDrawerProps> = ({
  user,
  groups = [],
  config,
  nextResetUtc,
  open,
  onClose,
  onSave,
}) => {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';

  const [selectedGroupId, setSelectedGroupId] = useState<string>('business-users');
  const [hasCustomQuota, setHasCustomQuota] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState<string>('10');
  const [customQuotaInput, setCustomQuotaInput] = useState<string>('10.00');
  const [customOverageInput, setCustomOverageInput] = useState<string>('2.00');
  const [isExempt, setIsExempt] = useState(false);
  const [isLocked, setIsLocked] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (user && config) {
      setSelectedGroupId(user.group_id || 'business-users');
      setHasCustomQuota(user.has_custom_quota);
      const quotaVal = user.custom_quota_usd ?? config.default_quota_usd;
      const overageVal = user.custom_overage_usd ?? config.default_overage_usd;

      setCustomQuotaInput(quotaVal.toFixed(2));
      setCustomOverageInput(overageVal.toFixed(2));

      if (config.preset_quotas.includes(quotaVal)) {
        setSelectedPreset(String(quotaVal));
      } else {
        setSelectedPreset('custom');
      }

      setIsExempt(user.is_exempt);
      setIsLocked(user.status === 'MANUALLY_DISABLED');
    }
  }, [user, config]);

  if (!user) return null;

  const handlePresetSelect = (val: number | 'custom') => {
    if (val === 'custom') {
      setSelectedPreset('custom');
    } else {
      setSelectedPreset(String(val));
      setCustomQuotaInput(val.toFixed(2));
    }
  };

  const handleSaveClick = async () => {
    setSaving(true);
    try {
      const quotaNum = parseFloat(customQuotaInput) || config?.default_quota_usd || 10.0;
      const overageNum = parseFloat(customOverageInput) || config?.default_overage_usd || 2.0;

      const payload: UserUpdatePayload = {
        group_id: selectedGroupId,
        has_custom_quota: hasCustomQuota,
        custom_quota_usd: hasCustomQuota ? quotaNum : null,
        custom_overage_usd: hasCustomQuota ? overageNum : null,
        is_exempt: isExempt,
        status: isLocked ? 'MANUALLY_DISABLED' : user.status === 'MANUALLY_DISABLED' ? 'ACTIVE' : user.status,
      };

      await onSave(user.email, payload);
      onClose();
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  const currentUsage = user.current_week;
  const breakdown = currentUsage.spend_breakdown;

  // Prepare model distribution for Donut chart
  const modelEntries = Object.entries(currentUsage.tokens_by_model);
  const totalModelTokens = modelEntries.reduce((sum, [, tokens]) => sum + tokens, 0);

  // SVG Donut calculation
  const radius = 52;
  const strokeWidth = 14;
  const circumference = 2 * Math.PI * radius;
  let accumulatedOffset = 0;

  const donutSegments = modelEntries.map(([model, tokens], idx) => {
    const fraction = totalModelTokens > 0 ? tokens / totalModelTokens : 0;
    const strokeDash = fraction * circumference;
    const offset = accumulatedOffset;
    accumulatedOffset += strokeDash;
    const color = MODEL_COLORS[idx % MODEL_COLORS.length];
    return {
      model,
      tokens,
      fraction,
      strokeDash,
      offset,
      color,
      spend: currentUsage.spend_by_model[model] || 0,
    };
  });

  // Hinge point tokens calculations
  const inputSpend = breakdown.input_spend_usd;
  const outputSpend = breakdown.output_spend_usd;
  const cachedSpend = breakdown.cached_spend_usd;
  const totalHingeSpend = inputSpend + outputSpend + cachedSpend || 1;

  const inputPct = (inputSpend / totalHingeSpend) * 100;
  const outputPct = (outputSpend / totalHingeSpend) * 100;
  const cachedPct = (cachedSpend / totalHingeSpend) * 100;

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        sx: {
          width: { xs: '100%', sm: 540 },
          p: 0,
          backgroundColor: isDark ? '#090d16' : '#f8fafc',
          borderLeft: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
        },
      }}
    >
      {/* Header */}
      <Box
        sx={{
          p: 2.5,
          backgroundColor: isDark ? '#111827' : '#ffffff',
          borderBottom: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.75 }}>
          <Avatar
            sx={{
              bgcolor: isDark ? 'rgba(99, 102, 241, 0.2)' : 'rgba(99, 102, 241, 0.1)',
              color: isDark ? '#c7d2fe' : '#4f46e5',
              border: `1px solid ${isDark ? 'rgba(99, 102, 241, 0.35)' : 'rgba(99, 102, 241, 0.25)'}`,
              width: 42,
              height: 42,
              fontWeight: 700,
            }}
          >
            {user.email.charAt(0).toUpperCase()}
          </Avatar>
          <Box>
            <Typography variant="subtitle1" sx={{ color: isDark ? '#f9fafb' : '#0f172a', fontWeight: 600 }}>
              {user.email}
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.25, flexWrap: 'wrap' }}>
              <Tooltip
                title={
                  user.status === 'AUTO_DISABLED'
                    ? nextResetUtc
                      ? `Over weekly quota limit. Automatically re-enables at weekly pool reset: ${new Date(nextResetUtc).toUTCString()}`
                      : 'Over weekly quota limit. Automatically re-enables on next credit pool reset.'
                    : user.status === 'MANUALLY_DISABLED'
                    ? 'Manually locked by administrator'
                    : 'Active user'
                }
                arrow
              >
                <Chip
                  label={user.status}
                  size="small"
                  sx={{
                    height: 20,
                    fontSize: '0.68rem',
                    fontWeight: 600,
                    backgroundColor:
                      user.status === 'ACTIVE'
                        ? isDark ? 'rgba(16, 185, 129, 0.15)' : 'rgba(16, 185, 129, 0.1)'
                        : isDark ? 'rgba(239, 68, 68, 0.15)' : 'rgba(239, 68, 68, 0.1)',
                    color: user.status === 'ACTIVE' ? '#10b981' : '#ef4444',
                  }}
                />
              </Tooltip>
              {user.status === 'AUTO_DISABLED' && nextResetUtc && (
                <Typography variant="caption" sx={{ color: '#ef4444', fontSize: '0.7rem', fontWeight: 600 }}>
                  Re-enables: {new Date(nextResetUtc).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                </Typography>
              )}
              {user.is_exempt && (
                <Chip
                  label="Exempt"
                  size="small"
                  sx={{
                    height: 20,
                    fontSize: '0.68rem',
                    fontWeight: 600,
                    backgroundColor: isDark ? 'rgba(99, 102, 241, 0.15)' : 'rgba(99, 102, 241, 0.1)',
                    color: '#818cf8',
                  }}
                />
              )}
            </Box>
          </Box>
        </Box>
        <IconButton onClick={onClose} size="small" sx={{ color: isDark ? '#9ca3af' : '#64748b' }}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Box>

      {/* Drawer Content */}
      <Box sx={{ p: 3, overflowY: 'auto', flexGrow: 1 }}>
        {/* Financial & Quota Ledger Section */}
        <Typography
          variant="caption"
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            mb: 1.5,
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            color: isDark ? '#9ca3af' : '#64748b',
          }}
        >
          <AccountBalanceWalletIcon sx={{ fontSize: 16, color: '#6366f1' }} />
          Financial & Quota Ledger ({currentUsage.week_id}
          {currentUsage.window_start_utc
            ? ` · Cycle started ${new Date(currentUsage.window_start_utc).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`
            : ''})
        </Typography>

        <Grid container spacing={1.5} sx={{ mb: 3 }}>
          <Grid item xs={6}>
            <Paper
              elevation={0}
              sx={{
                p: 2,
                backgroundColor: isDark ? '#111827' : '#ffffff',
                border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
              }}
            >
              <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b' }}>
                Gross Token Value
              </Typography>
              <Typography
                variant="h6"
                sx={{
                  fontWeight: 700,
                  fontFamily: 'monospace',
                  color: isDark ? '#f9fafb' : '#0f172a',
                }}
              >
                ${currentUsage.gross_spend_usd.toFixed(2)}
              </Typography>
              <Typography variant="caption" sx={{ color: isDark ? '#6b7280' : '#94a3b8' }}>
                {currentUsage.total_tokens.toLocaleString()} tokens
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={6}>
            <Paper
              elevation={0}
              sx={{
                p: 2,
                backgroundColor: isDark ? '#111827' : '#ffffff',
                border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
              }}
            >
              <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b' }}>
                Allocated Credits
              </Typography>
              <Typography
                variant="h6"
                sx={{
                  fontWeight: 700,
                  fontFamily: 'monospace',
                  color: '#6366f1',
                }}
              >
                ${currentUsage.quota_credits_usd.toFixed(2)}
              </Typography>
              <Typography variant="caption" sx={{ color: isDark ? '#6b7280' : '#94a3b8' }}>
                +${currentUsage.overage_buffer_usd.toFixed(2)} buffer
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={6}>
            <Paper
              elevation={0}
              sx={{
                p: 2,
                backgroundColor: isDark ? '#111827' : '#ffffff',
                border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
              }}
            >
              <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b' }}>
                Remaining Balance
              </Typography>
              <Typography
                variant="h6"
                sx={{
                  fontWeight: 700,
                  fontFamily: 'monospace',
                  color: '#10b981',
                }}
              >
                ${currentUsage.remaining_credit_usd.toFixed(2)}
              </Typography>
              <Typography variant="caption" sx={{ color: isDark ? '#6b7280' : '#94a3b8' }}>
                Available credit
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={6}>
            <Paper
              elevation={0}
              sx={{
                p: 2,
                backgroundColor: isDark ? '#111827' : '#ffffff',
                border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
              }}
            >
              <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b' }}>
                Net Quota Overage
              </Typography>
              <Typography
                variant="h6"
                sx={{
                  fontWeight: 700,
                  fontFamily: 'monospace',
                  color: currentUsage.net_billable_cost_usd > 0 ? '#ef4444' : isDark ? '#f9fafb' : '#0f172a',
                }}
              >
                ${currentUsage.net_billable_cost_usd.toFixed(2)}
              </Typography>
              <Typography variant="caption" sx={{ color: isDark ? '#6b7280' : '#94a3b8' }}>
                {currentUsage.net_billable_cost_usd > 0 ? 'Excess spend throttled' : 'Within granted quota'}
              </Typography>
            </Paper>
          </Grid>
        </Grid>

        {/* Interactive Model Breakdown with SVG Donut Chart */}
        <Typography
          variant="caption"
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            mb: 1.5,
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            color: isDark ? '#9ca3af' : '#64748b',
          }}
        >
          <DonutLargeIcon sx={{ fontSize: 16, color: '#6366f1' }} />
          Model Distribution & Spend Telemetry
        </Typography>

        <Paper
          elevation={0}
          sx={{
            p: 2.5,
            mb: 3,
            backgroundColor: isDark ? '#111827' : '#ffffff',
            border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
          }}
        >
          {donutSegments.length === 0 ? (
            <Typography variant="body2" sx={{ color: isDark ? '#9ca3af' : '#64748b', textAlign: 'center', py: 2 }}>
              No inference requests logged yet for this user.
            </Typography>
          ) : (
            <Box sx={{ display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, alignItems: 'center', gap: 3 }}>
              {/* SVG Donut Graphic */}
              <Box sx={{ position: 'relative', width: 140, height: 140, flexShrink: 0 }}>
                <svg width="140" height="140" viewBox="0 0 140 140">
                  <g transform="rotate(-90 70 70)">
                    {/* Background circle track */}
                    <circle
                      cx="70"
                      cy="70"
                      r={radius}
                      fill="transparent"
                      stroke={isDark ? 'rgba(255, 255, 255, 0.06)' : '#e2e8f0'}
                      strokeWidth={strokeWidth}
                    />
                    {donutSegments.map((seg, i) => (
                      <circle
                        key={i}
                        cx="70"
                        cy="70"
                        r={radius}
                        fill="transparent"
                        stroke={seg.color}
                        strokeWidth={strokeWidth}
                        strokeDasharray={`${seg.strokeDash} ${circumference}`}
                        strokeDashoffset={-seg.offset}
                        strokeLinecap="round"
                        style={{ transition: 'stroke-dasharray 0.5s ease' }}
                      />
                    ))}
                  </g>
                </svg>
                {/* Center text */}
                <Box
                  sx={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Typography
                    variant="caption"
                    sx={{
                      fontSize: '0.68rem',
                      color: isDark ? '#9ca3af' : '#64748b',
                      textTransform: 'uppercase',
                    }}
                  >
                    Gross
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{
                      fontWeight: 700,
                      fontFamily: 'monospace',
                      color: isDark ? '#f9fafb' : '#0f172a',
                    }}
                  >
                    ${currentUsage.gross_spend_usd.toFixed(2)}
                  </Typography>
                </Box>
              </Box>

              {/* Model Legend & Metrics */}
              <Box sx={{ flexGrow: 1, width: '100%' }}>
                {donutSegments.map((seg) => (
                  <Box key={seg.model} sx={{ mb: 1.5, '&:last-child': { mb: 0 } }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Box
                          sx={{
                            width: 10,
                            height: 10,
                            borderRadius: '50%',
                            backgroundColor: seg.color,
                          }}
                        />
                        <Typography variant="body2" sx={{ fontWeight: 600, fontSize: '0.82rem' }}>
                          {seg.model}
                        </Typography>
                      </Box>
                      <Typography
                        variant="caption"
                        sx={{
                          fontFamily: 'monospace',
                          fontWeight: 600,
                          color: isDark ? '#cbd5e1' : '#334155',
                        }}
                      >
                        ${seg.spend.toFixed(2)} ({(seg.fraction * 100).toFixed(0)}%)
                      </Typography>
                    </Box>
                    <Typography
                      variant="caption"
                      sx={{ color: isDark ? '#6b7280' : '#94a3b8', display: 'block', pl: 2.25, fontSize: '0.72rem' }}
                    >
                      {seg.tokens.toLocaleString()} tokens
                    </Typography>
                  </Box>
                ))}
              </Box>
            </Box>
          )}
        </Paper>

        {/* Hinge Point Breakdown Bar */}
        <Typography
          variant="caption"
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            mb: 1.5,
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            color: isDark ? '#9ca3af' : '#64748b',
          }}
        >
          Hinge Point Cost Distribution
        </Typography>

        <Paper
          elevation={0}
          sx={{
            p: 2,
            mb: 3,
            backgroundColor: isDark ? '#111827' : '#ffffff',
            border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
          }}
        >
          {/* Segmented Meter Bar */}
          <Box
            sx={{
              display: 'flex',
              height: 10,
              borderRadius: 5,
              overflow: 'hidden',
              backgroundColor: isDark ? 'rgba(255, 255, 255, 0.06)' : '#e2e8f0',
              mb: 2,
            }}
          >
            <Box sx={{ width: `${inputPct}%`, backgroundColor: '#6366f1' }} />
            <Box sx={{ width: `${outputPct}%`, backgroundColor: '#a855f7' }} />
            <Box sx={{ width: `${cachedPct}%`, backgroundColor: '#10b981' }} />
          </Box>

          <Grid container spacing={1.5}>
            <Grid item xs={4}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.25 }}>
                <Box sx={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: '#6366f1' }} />
                <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b', fontSize: '0.72rem' }}>
                  Prompt / Input
                </Typography>
              </Box>
              <Typography variant="body2" sx={{ fontWeight: 600, fontFamily: 'monospace', pl: 1.75 }}>
                ${breakdown.input_spend_usd.toFixed(2)}
              </Typography>
            </Grid>
            <Grid item xs={4}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.25 }}>
                <Box sx={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: '#a855f7' }} />
                <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b', fontSize: '0.72rem' }}>
                  Completion / Output
                </Typography>
              </Box>
              <Typography variant="body2" sx={{ fontWeight: 600, fontFamily: 'monospace', pl: 1.75 }}>
                ${breakdown.output_spend_usd.toFixed(2)}
              </Typography>
            </Grid>
            <Grid item xs={4}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.25 }}>
                <Box sx={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: '#10b981' }} />
                <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b', fontSize: '0.72rem' }}>
                  Context Cache
                </Typography>
              </Box>
              <Typography variant="body2" sx={{ fontWeight: 600, fontFamily: 'monospace', pl: 1.75 }}>
                ${breakdown.cached_spend_usd.toFixed(2)}
              </Typography>
            </Grid>
          </Grid>
        </Paper>

        {/* Quota Management Controls */}
        <Typography
          variant="caption"
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            mb: 1.5,
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            color: isDark ? '#9ca3af' : '#64748b',
          }}
        >
          <TuneIcon sx={{ fontSize: 16, color: '#6366f1' }} />
          User Quota & Governance Overrides
        </Typography>

        <Paper
          elevation={0}
          sx={{
            p: 2.5,
            backgroundColor: isDark ? '#111827' : '#ffffff',
            border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
          }}
        >
          {/* Quota Management Group Selection */}
          <Box sx={{ mb: 2.5 }}>
            <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b', fontWeight: 600, mb: 1, display: 'block' }}>
              QUOTA MANAGEMENT GROUP
            </Typography>
            <TextField
              select
              size="small"
              fullWidth
              value={selectedGroupId}
              onChange={(e) => setSelectedGroupId(e.target.value)}
              helperText={`Baseline quota: $${(
                groups.find((g) => g.group_id === selectedGroupId)?.weekly_quota_usd ??
                config?.default_quota_usd ??
                10
              ).toFixed(2)}/wk${
                groups.find((g) => g.group_id === selectedGroupId)?.is_exempt ? ' • Group is exempt from throttling' : ''
              }`}
            >
              {groups.map((g) => (
                <MenuItem key={g.group_id} value={g.group_id}>
                  {g.display_name} (${g.weekly_quota_usd.toFixed(2)}/wk {g.is_exempt ? '• Exempt' : ''})
                </MenuItem>
              ))}
            </TextField>

            {hasCustomQuota && (
              <Box
                sx={{
                  mt: 1.5,
                  p: 1.5,
                  borderRadius: 2,
                  backgroundColor: isDark ? 'rgba(245, 158, 11, 0.1)' : '#fef3c7',
                  border: `1px solid ${isDark ? 'rgba(245, 158, 11, 0.25)' : '#fde68a'}`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 1.5,
                  flexWrap: 'wrap',
                }}
              >
                <Typography variant="caption" sx={{ color: isDark ? '#fbbf24' : '#92400e', fontWeight: 600, flex: 1 }}>
                  ⚠️ Custom Override Active: User will not inherit {groups.find((g) => g.group_id === selectedGroupId)?.display_name || 'Group'} baseline (${(groups.find((g) => g.group_id === selectedGroupId)?.weekly_quota_usd ?? config?.default_quota_usd ?? 10).toFixed(2)}/wk) unless override is removed.
                </Typography>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => {
                    setHasCustomQuota(false);
                    const targetGroup = groups.find((g) => g.group_id === selectedGroupId);
                    if (targetGroup) {
                      setCustomQuotaInput(targetGroup.weekly_quota_usd.toFixed(2));
                      setCustomOverageInput(targetGroup.overage_buffer_usd.toFixed(2));
                    }
                  }}
                  sx={{
                    textTransform: 'none',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    borderColor: isDark ? '#f59e0b' : '#d97706',
                    color: isDark ? '#fbbf24' : '#b45309',
                    py: 0.25,
                    px: 1,
                    '&:hover': {
                      borderColor: isDark ? '#fbbf24' : '#92400e',
                      backgroundColor: isDark ? 'rgba(245, 158, 11, 0.2)' : '#fde68a',
                    },
                  }}
                >
                  Adopt Group Quota
                </Button>
              </Box>
            )}
          </Box>

          <Divider sx={{ mb: 2 }} />

          {/* Custom Quota Toggle */}
          <FormControlLabel
            control={
              <Switch
                checked={hasCustomQuota}
                onChange={(e) => setHasCustomQuota(e.target.checked)}
                color="primary"
              />
            }
            label={
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  Enable Custom Quota Override for this User
                </Typography>
                <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b' }}>
                  Overrides group baseline quota with user-specific spend and overage limits
                </Typography>
              </Box>
            }
            sx={{ mb: 2, alignItems: 'flex-start', ml: 0 }}
          />

          {hasCustomQuota && (
            <Box sx={{ pl: 4, mb: 3 }}>
              <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b', fontWeight: 600, mb: 1, display: 'block' }}>
                Preset Weekly Credit Allowances
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 2 }}>
                {(config?.preset_quotas || [5, 10, 20, 50]).map((preset) => (
                  <Chip
                    key={preset}
                    label={`$${preset}/wk`}
                    clickable
                    onClick={() => handlePresetSelect(preset)}
                    size="small"
                    sx={{
                      fontWeight: selectedPreset === String(preset) ? 700 : 500,
                      backgroundColor:
                        selectedPreset === String(preset)
                          ? '#6366f1'
                          : isDark ? 'rgba(255, 255, 255, 0.05)' : '#f1f5f9',
                      color: selectedPreset === String(preset) ? '#ffffff' : isDark ? '#cbd5e1' : '#334155',
                      border: `1px solid ${
                        selectedPreset === String(preset) ? 'transparent' : isDark ? 'rgba(255, 255, 255, 0.08)' : '#cbd5e1'
                      }`,
                    }}
                  />
                ))}
                <Chip
                  label="Custom"
                  clickable
                  onClick={() => handlePresetSelect('custom')}
                  size="small"
                  sx={{
                    fontWeight: selectedPreset === 'custom' ? 700 : 500,
                    backgroundColor:
                      selectedPreset === 'custom'
                        ? '#6366f1'
                        : isDark ? 'rgba(255, 255, 255, 0.05)' : '#f1f5f9',
                    color: selectedPreset === 'custom' ? '#ffffff' : isDark ? '#cbd5e1' : '#334155',
                  }}
                />
              </Box>

              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <TextField
                    label="Weekly Quota ($)"
                    type="number"
                    size="small"
                    fullWidth
                    value={customQuotaInput}
                    onChange={(e) => {
                      setCustomQuotaInput(e.target.value);
                      setSelectedPreset('custom');
                    }}
                    InputProps={{
                      startAdornment: <InputAdornment position="start">$</InputAdornment>,
                    }}
                  />
                </Grid>
                <Grid item xs={6}>
                  <TextField
                    label="Overage Buffer ($)"
                    type="number"
                    size="small"
                    fullWidth
                    value={customOverageInput}
                    onChange={(e) => setCustomOverageInput(e.target.value)}
                    InputProps={{
                      startAdornment: <InputAdornment position="start">$</InputAdornment>,
                    }}
                  />
                </Grid>
              </Grid>
            </Box>
          )}

          <Divider sx={{ my: 2 }} />

          {/* Exemption Toggle */}
          <FormControlLabel
            control={
              <Switch
                checked={isExempt}
                onChange={(e) => setIsExempt(e.target.checked)}
                color="secondary"
              />
            }
            label={
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  Exempt from Automatic Quota Throttling
                </Typography>
                <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b' }}>
                  User will never be moved to antigravity-throttled@, even if quota is breached.
                </Typography>
              </Box>
            }
            sx={{ mb: 2, alignItems: 'flex-start', ml: 0 }}
          />

          {/* Manual Lock Toggle */}
          <FormControlLabel
            control={
              <Switch
                checked={isLocked}
                onChange={(e) => setIsLocked(e.target.checked)}
                color="error"
              />
            }
            label={
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  Manually Lock User
                </Typography>
                <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b' }}>
                  Immediately demotes to antigravity-throttled@, revoking Antigravity IDE access.
                </Typography>
              </Box>
            }
            sx={{ alignItems: 'flex-start', ml: 0 }}
          />
        </Paper>
      </Box>

      {/* Footer Actions */}
      <Box
        sx={{
          p: 2,
          backgroundColor: isDark ? '#111827' : '#ffffff',
          borderTop: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
          display: 'flex',
          justifyContent: 'flex-end',
          gap: 1.5,
        }}
      >
        <Button variant="outlined" onClick={onClose} disabled={saving} sx={{ borderRadius: 2 }}>
          Cancel
        </Button>
        <Button
          variant="contained"
          startIcon={<SaveIcon />}
          onClick={handleSaveClick}
          disabled={saving}
          sx={{
            borderRadius: 2,
            backgroundColor: '#6366f1',
            '&:hover': { backgroundColor: '#4f46e5' },
          }}
        >
          {saving ? 'Saving...' : 'Save Changes'}
        </Button>
      </Box>
    </Drawer>
  );
};
