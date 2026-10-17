import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  Grid,
  IconButton,
  InputAdornment,
  MenuItem,
  Paper,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import SpeedIcon from '@mui/icons-material/Speed';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import BlockIcon from '@mui/icons-material/Block';
import {
  QuotaGroup,
  QuotaRequestCreatePayload,
  QuotaRequestDuration,
  QuotaRequestReasonCategory,
  User,
} from '../types';

export interface RequestQuotaModalProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (payload: QuotaRequestCreatePayload) => Promise<void>;
  user: User | null;
  group?: QuotaGroup | null;
}

const REASON_CATEGORIES: { value: QuotaRequestReasonCategory; label: string; description: string }[] = [
  {
    value: 'SPRINT_DEADLINE',
    label: '🚀 Active Sprint / Tight Deadline',
    description: 'Upcoming delivery deadline requiring high token throughput',
  },
  {
    value: 'REFACTORING',
    label: '🛠️ Heavy Refactoring / Large Context',
    description: 'Large codebase indexing or multi-file architecture refactor',
  },
  {
    value: 'INCIDENT',
    label: '🚨 Production Incident / Hotfix',
    description: 'Active production outage or urgent root cause investigation',
  },
  {
    value: 'ROLE_UPGRADE',
    label: '👥 Role Change / Need Tier Upgrade',
    description: 'Transitioned to new team or role requiring higher baseline',
  },
  {
    value: 'OTHER',
    label: '📝 Other Project Need',
    description: 'Custom research, model benchmarking, or exploratory prototype',
  },
];

export const RequestQuotaModal: React.FC<RequestQuotaModalProps> = ({
  open,
  onClose,
  onSubmit,
  user,
  group,
}) => {
  const currentQuota = user?.has_custom_quota && user.custom_quota_usd != null
    ? user.custom_quota_usd
    : (group?.weekly_quota_usd ?? 50.0);
  const currentSpend = user?.current_week.gross_spend_usd ?? 0.0;

  // Preset increments
  const p15 = currentQuota + 15;
  const p25 = currentQuota + 25;
  const p50 = currentQuota + 50;

  const [category, setCategory] = useState<QuotaRequestReasonCategory>('SPRINT_DEADLINE');
  const [quotaSelection, setQuotaSelection] = useState<'p15' | 'p25' | 'p50' | 'custom'>('p25');
  const [customAmount, setCustomAmount] = useState<string>(String(p25));
  const [duration, setDuration] = useState<QuotaRequestDuration>('TEMPORARY_WEEKLY');
  const [justification, setJustification] = useState<string>('');
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string>('');

  // Reset form when modal opens
  useEffect(() => {
    if (open) {
      setCategory('SPRINT_DEADLINE');
      setQuotaSelection('p25');
      setCustomAmount(String(currentQuota + 25));
      setDuration('TEMPORARY_WEEKLY');
      setJustification('');
      setError('');
      setSubmitting(false);
    }
  }, [open, currentQuota]);

  const getEffectiveRequestedAmount = (): number => {
    if (quotaSelection === 'p15') return p15;
    if (quotaSelection === 'p25') return p25;
    if (quotaSelection === 'p50') return p50;
    const parsed = parseFloat(customAmount);
    return isNaN(parsed) ? 0 : parsed;
  };

  const handleSubmit = async () => {
    setError('');
    const requestedAmount = getEffectiveRequestedAmount();

    if (requestedAmount <= 0) {
      setError('Please specify a requested quota amount greater than $0.');
      return;
    }
    if (requestedAmount <= currentQuota) {
      setError(`Requested quota ($${requestedAmount.toFixed(2)}) must be greater than your current allowance ($${currentQuota.toFixed(2)}).`);
      return;
    }
    if (!justification.trim() || justification.trim().length < 10) {
      setError('Please provide a business justification (at least 10 characters).');
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit({
        requested_quota_usd: requestedAmount,
        reason_category: category,
        justification: justification.trim(),
        duration_needed: duration,
      });
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to submit quota increase request.');
    } finally {
      setSubmitting(false);
    }
  };

  const getStatusBadge = () => {
    if (!user) return null;
    if (user.is_exempt) {
      return <Chip size="small" label="EXEMPT" sx={{ bgcolor: 'rgba(156, 163, 175, 0.2)', color: '#9ca3af', fontWeight: 600 }} />;
    }
    if (user.status === 'AUTO_DISABLED') {
      return (
        <Chip
          size="small"
          icon={<WarningAmberIcon sx={{ fontSize: 16 }} />}
          label="AUTO-THROTTLED"
          sx={{ bgcolor: 'rgba(245, 158, 11, 0.2)', color: '#f59e0b', fontWeight: 600 }}
        />
      );
    }
    if (user.status === 'MANUALLY_DISABLED') {
      return (
        <Chip
          size="small"
          icon={<BlockIcon sx={{ fontSize: 16 }} />}
          label="MANUALLY LOCKED"
          sx={{ bgcolor: 'rgba(239, 68, 68, 0.2)', color: '#ef4444', fontWeight: 600 }}
        />
      );
    }
    return (
      <Chip
        size="small"
        icon={<CheckCircleOutlineIcon sx={{ fontSize: 16 }} />}
        label="ACTIVE"
        sx={{ bgcolor: 'rgba(16, 185, 129, 0.2)', color: '#10b981', fontWeight: 600 }}
      />
    );
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
      <DialogTitle
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          pb: 1.5,
          borderBottom: '1px solid',
          borderColor: 'divider',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Box
            sx={{
              width: 38,
              height: 38,
              borderRadius: '10px',
              bgcolor: 'rgba(99, 102, 241, 0.15)',
              color: 'primary.main',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <TrendingUpIcon />
          </Box>
          <Box>
            <Typography variant="h6" sx={{ fontSize: '1.05rem', fontWeight: 700 }}>
              Request Quota Increase
            </Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
              Submit an in-app quota increase for immediate admin review
            </Typography>
          </Box>
        </Box>
        <IconButton size="small" onClick={onClose} disabled={submitting}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>

      <DialogContent sx={{ pt: 2.5, pb: 2 }}>
        {error && (
          <Alert severity="error" sx={{ mb: 2.5, borderRadius: 2 }} onClose={() => setError('')}>
            {error}
          </Alert>
        )}

        {/* Current Status Overview Card */}
        <Paper
          variant="outlined"
          sx={{
            p: 2,
            mb: 3,
            borderRadius: 2,
            bgcolor: (theme) => (theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.03)' : '#f8fafc'),
            borderColor: 'divider',
          }}
        >
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} sm={6}>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', mb: 0.5 }}>
                DEVELOPER ACCOUNT
              </Typography>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {user?.email || 'Current Developer'}
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                Group: {group?.display_name || user?.group_id || 'Business Users'}
              </Typography>
            </Grid>

            <Grid item xs={6} sm={3}>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', mb: 0.5 }}>
                CURRENT SPEND
              </Typography>
              <Typography variant="body2" sx={{ fontWeight: 700, color: currentSpend >= currentQuota ? 'error.main' : 'text.primary' }}>
                ${currentSpend.toFixed(2)}
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                Allowance: ${currentQuota.toFixed(2)}/wk
              </Typography>
            </Grid>

            <Grid item xs={6} sm={3} sx={{ textAlign: { sm: 'right' } }}>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', mb: 0.5 }}>
                LIVE STATUS
              </Typography>
              <Box>{getStatusBadge()}</Box>
            </Grid>
          </Grid>
        </Paper>

        <Stack spacing={3}>
          {/* 1. Reason Category */}
          <FormControl fullWidth size="small">
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.75 }}>
              1. Reason Category
            </Typography>
            <TextField
              select
              size="small"
              value={category}
              onChange={(e) => setCategory(e.target.value as QuotaRequestReasonCategory)}
              helperText={REASON_CATEGORIES.find((r) => r.value === category)?.description}
            >
              {REASON_CATEGORIES.map((cat) => (
                <MenuItem key={cat.value} value={cat.value}>
                  {cat.label}
                </MenuItem>
              ))}
            </TextField>
          </FormControl>

          {/* 2. Requested Weekly Quota */}
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.75 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                2. Requested Weekly Quota ($)
              </Typography>
              <Typography variant="caption" sx={{ color: 'primary.main', fontWeight: 600 }}>
                Target: ${getEffectiveRequestedAmount().toFixed(2)}/wk
              </Typography>
            </Box>

            <RadioGroup
              row
              value={quotaSelection}
              onChange={(e) => {
                const val = e.target.value as 'p15' | 'p25' | 'p50' | 'custom';
                setQuotaSelection(val);
                if (val === 'p15') setCustomAmount(String(p15));
                if (val === 'p25') setCustomAmount(String(p25));
                if (val === 'p50') setCustomAmount(String(p50));
              }}
              sx={{ gap: 1, mb: 1.5 }}
            >
              <Paper
                variant="outlined"
                sx={{
                  px: 1.5,
                  py: 0.5,
                  borderRadius: 2,
                  borderColor: quotaSelection === 'p15' ? 'primary.main' : 'divider',
                  bgcolor: quotaSelection === 'p15' ? 'rgba(99, 102, 241, 0.08)' : 'transparent',
                  flexGrow: 1,
                }}
              >
                <FormControlLabel
                  value="p15"
                  control={<Radio size="small" />}
                  label={<Typography variant="body2" sx={{ fontWeight: 600 }}>+$15 (${p15})</Typography>}
                />
              </Paper>

              <Paper
                variant="outlined"
                sx={{
                  px: 1.5,
                  py: 0.5,
                  borderRadius: 2,
                  borderColor: quotaSelection === 'p25' ? 'primary.main' : 'divider',
                  bgcolor: quotaSelection === 'p25' ? 'rgba(99, 102, 241, 0.08)' : 'transparent',
                  flexGrow: 1,
                }}
              >
                <FormControlLabel
                  value="p25"
                  control={<Radio size="small" />}
                  label={<Typography variant="body2" sx={{ fontWeight: 600 }}>+$25 (${p25})</Typography>}
                />
              </Paper>

              <Paper
                variant="outlined"
                sx={{
                  px: 1.5,
                  py: 0.5,
                  borderRadius: 2,
                  borderColor: quotaSelection === 'p50' ? 'primary.main' : 'divider',
                  bgcolor: quotaSelection === 'p50' ? 'rgba(99, 102, 241, 0.08)' : 'transparent',
                  flexGrow: 1,
                }}
              >
                <FormControlLabel
                  value="p50"
                  control={<Radio size="small" />}
                  label={<Typography variant="body2" sx={{ fontWeight: 600 }}>+$50 (${p50})</Typography>}
                />
              </Paper>

              <Paper
                variant="outlined"
                sx={{
                  px: 1.5,
                  py: 0.5,
                  borderRadius: 2,
                  borderColor: quotaSelection === 'custom' ? 'primary.main' : 'divider',
                  bgcolor: quotaSelection === 'custom' ? 'rgba(99, 102, 241, 0.08)' : 'transparent',
                  flexGrow: 1,
                }}
              >
                <FormControlLabel
                  value="custom"
                  control={<Radio size="small" />}
                  label={<Typography variant="body2" sx={{ fontWeight: 600 }}>Custom</Typography>}
                />
              </Paper>
            </RadioGroup>

            {quotaSelection === 'custom' && (
              <TextField
                fullWidth
                size="small"
                type="number"
                label="Custom Weekly Quota Limit"
                value={customAmount}
                onChange={(e) => setCustomAmount(e.target.value)}
                InputProps={{
                  startAdornment: <InputAdornment position="start">$</InputAdornment>,
                  endAdornment: <InputAdornment position="end">/week</InputAdornment>,
                }}
                helperText={`Must be greater than current allowance of $${currentQuota.toFixed(2)}/wk.`}
                sx={{ mt: 1 }}
              />
            )}
          </Box>

          {/* 3. Duration Needed */}
          <Box>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.75 }}>
              3. Duration Needed
            </Typography>
            <RadioGroup
              value={duration}
              onChange={(e) => setDuration(e.target.value as QuotaRequestDuration)}
              sx={{ gap: 1 }}
            >
              <Paper
                variant="outlined"
                sx={{
                  p: 1.25,
                  borderRadius: 2,
                  borderColor: duration === 'TEMPORARY_WEEKLY' ? 'primary.main' : 'divider',
                  bgcolor: duration === 'TEMPORARY_WEEKLY' ? 'rgba(99, 102, 241, 0.06)' : 'transparent',
                }}
              >
                <FormControlLabel
                  value="TEMPORARY_WEEKLY"
                  control={<Radio size="small" />}
                  label={
                    <Box>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        Temporary (This week only)
                      </Typography>
                      <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                        Reverts automatically back to your group quota ($ {currentQuota.toFixed(2)}/wk) upon Cloud Monitoring weekly reset
                      </Typography>
                    </Box>
                  }
                  sx={{ m: 0, width: '100%' }}
                />
              </Paper>

              <Paper
                variant="outlined"
                sx={{
                  p: 1.25,
                  borderRadius: 2,
                  borderColor: duration === 'PERMANENT' ? 'primary.main' : 'divider',
                  bgcolor: duration === 'PERMANENT' ? 'rgba(99, 102, 241, 0.06)' : 'transparent',
                }}
              >
                <FormControlLabel
                  value="PERMANENT"
                  control={<Radio size="small" />}
                  label={
                    <Box>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        Permanent Upgrade
                      </Typography>
                      <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                        Maintains this custom quota across future billing and weekly reset cycles
                      </Typography>
                    </Box>
                  }
                  sx={{ m: 0, width: '100%' }}
                />
              </Paper>
            </RadioGroup>
          </Box>

          {/* 4. Business Justification */}
          <Box>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.75 }}>
              4. Business Justification / Project Context
            </Typography>
            <TextField
              fullWidth
              multiline
              rows={3}
              placeholder="e.g. Critical sprint deadline delivery for Payment Services; refactoring gRPC services with high token prompt context and multi-turn agent runs."
              value={justification}
              onChange={(e) => setJustification(e.target.value)}
              helperText="Provide context for your team lead and platform administrators to approve promptly."
            />
          </Box>
        </Stack>
      </DialogContent>

      <DialogActions sx={{ px: 3, py: 2, borderTop: '1px solid', borderColor: 'divider' }}>
        <Button onClick={onClose} disabled={submitting}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handleSubmit}
          disabled={submitting}
          startIcon={submitting ? <CircularProgress size={16} color="inherit" /> : <SpeedIcon fontSize="small" />}
          sx={{
            fontWeight: 600,
            px: 2.5,
          }}
        >
          {submitting ? 'Submitting...' : 'Submit Request'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
