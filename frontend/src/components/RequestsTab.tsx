import React, { useEffect, useState } from 'react';
import {
  Alert,
  Avatar,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  InputAdornment,
  Paper,
  Radio,
  RadioGroup,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  Tabs,
  TextField,
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CancelIcon from '@mui/icons-material/Cancel';
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty';
import RefreshIcon from '@mui/icons-material/Refresh';
import CloseIcon from '@mui/icons-material/Close';
import DoneAllIcon from '@mui/icons-material/DoneAll';
import CheckIcon from '@mui/icons-material/Check';
import ClearIcon from '@mui/icons-material/Clear';
import {
  bulkReviewQuotaRequests,
  fetchQuotaRequests,
  reviewQuotaRequest,
} from '../services/api';
import {
  QuotaRequest,
  QuotaRequestBulkReviewPayload,
  QuotaRequestDuration,
  QuotaRequestReasonCategory,
  QuotaRequestReviewPayload,
  QuotaRequestStatus,
} from '../types';

export interface RequestsTabProps {
  requests?: QuotaRequest[];
  loading?: boolean;
  onRefresh?: () => void;
  onApprove?: (requestId: string, payload: QuotaRequestReviewPayload) => Promise<void>;
  onReject?: (requestId: string, payload: QuotaRequestReviewPayload) => Promise<void>;
  onBulkApprove?: (payload: QuotaRequestBulkReviewPayload) => Promise<void>;
}

export const RequestsTab: React.FC<RequestsTabProps> = ({
  requests: propRequests,
  loading: propLoading,
  onRefresh: propOnRefresh,
  onApprove: propOnApprove,
  onReject: propOnReject,
  onBulkApprove: propOnBulkApprove,
}) => {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';

  const [internalRequests, setInternalRequests] = useState<QuotaRequest[]>([]);
  const [internalLoading, setInternalLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [successMessage, setSuccessMessage] = useState<string>('');

  // Active sub-tab filter: 'PENDING' | 'APPROVED' | 'REJECTED' | 'ALL'
  const [activeTab, setActiveTab] = useState<'PENDING' | 'APPROVED' | 'REJECTED' | 'ALL'>('PENDING');

  // Search filter
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Multi-select for bulk actions
  const [selectedRequestIds, setSelectedRequestIds] = useState<string[]>([]);

  // Pagination
  const [page, setPage] = useState<number>(0);
  const [rowsPerPage, setRowsPerPage] = useState<number>(10);

  // Single Approval Dialog State
  const [approvalModalOpen, setApprovalModalOpen] = useState<boolean>(false);
  const [selectedRequestForApproval, setSelectedRequestForApproval] = useState<QuotaRequest | null>(null);
  const [approvedAmount, setApprovedAmount] = useState<string>('');
  const [approvedDuration, setApprovedDuration] = useState<QuotaRequestDuration>('TEMPORARY_WEEKLY');
  const [approvalNote, setApprovalNote] = useState<string>('');
  const [approving, setApproving] = useState<boolean>(false);

  // Single Rejection Dialog State
  const [rejectionModalOpen, setRejectionModalOpen] = useState<boolean>(false);
  const [selectedRequestForRejection, setSelectedRequestForRejection] = useState<QuotaRequest | null>(null);
  const [rejectionReason, setRejectionReason] = useState<string>('');
  const [rejecting, setRejecting] = useState<boolean>(false);

  // Bulk Approval Dialog State
  const [bulkModalOpen, setBulkModalOpen] = useState<boolean>(false);
  const [bulkDuration, setBulkDuration] = useState<QuotaRequestDuration>('TEMPORARY_WEEKLY');
  const [bulkNote, setBulkNote] = useState<string>('');
  const [bulkApproving, setBulkApproving] = useState<boolean>(false);

  // Load requests
  const loadRequests = async () => {
    if (propRequests) {
      if (propOnRefresh) propOnRefresh();
      return;
    }
    setInternalLoading(true);
    setError('');
    try {
      const data = await fetchQuotaRequests();
      setInternalRequests(data);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch quota requests');
    } finally {
      setInternalLoading(false);
    }
  };

  useEffect(() => {
    if (!propRequests) {
      loadRequests();
    }
  }, [propRequests]);

  const requests = propRequests ?? internalRequests;
  const isLoading = propLoading ?? internalLoading;

  // Relative Time Formatter
  const formatRelativeTime = (isoString: string): string => {
    if (!isoString) return '';
    try {
      const date = new Date(isoString);
      const now = new Date();
      const diffSec = Math.floor((now.getTime() - date.getTime()) / 1000);

      if (diffSec < 60) return 'Just now';
      const diffMin = Math.floor(diffSec / 60);
      if (diffMin < 60) return `${diffMin}m ago`;
      const diffHours = Math.floor(diffMin / 60);
      if (diffHours < 24) return `${diffHours}h ago`;
      const diffDays = Math.floor(diffHours / 24);
      if (diffDays < 7) return `${diffDays}d ago`;
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch {
      return isoString;
    }
  };

  // Reason Category Helper
  const getCategoryDetails = (cat: QuotaRequestReasonCategory): { label: string; icon: string } => {
    switch (cat) {
      case 'SPRINT_DEADLINE':
        return { label: 'Sprint Deadline', icon: '🚀' };
      case 'REFACTORING':
        return { label: 'Refactoring', icon: '🛠️' };
      case 'INCIDENT':
        return { label: 'Incident / Hotfix', icon: '🚨' };
      case 'ROLE_UPGRADE':
        return { label: 'Role Upgrade', icon: '👥' };
      case 'OTHER':
      default:
        return { label: 'Other Need', icon: '📝' };
    }
  };

  // Status Chip Renderer
  const renderStatusChip = (status: QuotaRequestStatus) => {
    switch (status) {
      case 'PENDING':
        return (
          <Chip
            size="small"
            icon={<HourglassEmptyIcon sx={{ fontSize: '14px !important', color: '#f59e0b !important' }} />}
            label="PENDING"
            sx={{
              fontWeight: 700,
              fontSize: '0.72rem',
              bgcolor: isDark ? 'rgba(245, 158, 11, 0.15)' : 'rgba(245, 158, 11, 0.12)',
              color: '#f59e0b',
              border: '1px solid rgba(245, 158, 11, 0.3)',
            }}
          />
        );
      case 'APPROVED':
        return (
          <Chip
            size="small"
            icon={<CheckCircleIcon sx={{ fontSize: '14px !important', color: '#10b981 !important' }} />}
            label="APPROVED"
            sx={{
              fontWeight: 700,
              fontSize: '0.72rem',
              bgcolor: isDark ? 'rgba(16, 185, 129, 0.15)' : 'rgba(16, 185, 129, 0.12)',
              color: '#10b981',
              border: '1px solid rgba(16, 185, 129, 0.3)',
            }}
          />
        );
      case 'REJECTED':
        return (
          <Chip
            size="small"
            icon={<CancelIcon sx={{ fontSize: '14px !important', color: '#ef4444 !important' }} />}
            label="REJECTED"
            sx={{
              fontWeight: 700,
              fontSize: '0.72rem',
              bgcolor: isDark ? 'rgba(239, 68, 68, 0.15)' : 'rgba(239, 68, 68, 0.12)',
              color: '#ef4444',
              border: '1px solid rgba(239, 68, 68, 0.3)',
            }}
          />
        );
      case 'CANCELLED':
      default:
        return (
          <Chip
            size="small"
            label="CANCELLED"
            sx={{
              fontWeight: 700,
              fontSize: '0.72rem',
              bgcolor: isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.08)',
              color: 'text.secondary',
              border: '1px solid',
              borderColor: 'divider',
            }}
          />
        );
    }
  };

  // Filter requests
  const filteredRequests = requests.filter((req) => {
    // Status Filter
    if (activeTab !== 'ALL' && req.status !== activeTab) {
      return false;
    }
    // Search Query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (
        req.user_email.toLowerCase().includes(q) ||
        req.reason_category.toLowerCase().includes(q) ||
        req.justification.toLowerCase().includes(q) ||
        req.current_group_id.toLowerCase().includes(q)
      );
    }
    return true;
  });

  // Counts
  const pendingCount = requests.filter((r) => r.status === 'PENDING').length;
  const approvedCount = requests.filter((r) => r.status === 'APPROVED').length;
  const rejectedCount = requests.filter((r) => r.status === 'REJECTED').length;
  const allCount = requests.length;

  // Pending items currently selectable
  const pendingRequestsInCurrentView = filteredRequests.filter((r) => r.status === 'PENDING');
  const allPendingSelected =
    pendingRequestsInCurrentView.length > 0 &&
    pendingRequestsInCurrentView.every((r) => selectedRequestIds.includes(r.request_id));

  const handleSelectAllToggle = () => {
    if (allPendingSelected) {
      setSelectedRequestIds([]);
    } else {
      const ids = pendingRequestsInCurrentView.map((r) => r.request_id);
      setSelectedRequestIds(ids);
    }
  };

  const handleToggleSelectRow = (requestId: string) => {
    setSelectedRequestIds((prev) =>
      prev.includes(requestId) ? prev.filter((id) => id !== requestId) : [...prev, requestId]
    );
  };

  // Open Approval Dialog
  const handleOpenApproveDialog = (req: QuotaRequest) => {
    setSelectedRequestForApproval(req);
    setApprovedAmount(String(req.requested_quota_usd));
    setApprovedDuration(req.duration_needed || 'TEMPORARY_WEEKLY');
    setApprovalNote('');
    setApprovalModalOpen(true);
  };

  // Confirm Single Approval
  const handleConfirmApproval = async () => {
    if (!selectedRequestForApproval) return;
    const amount = parseFloat(approvedAmount);
    if (isNaN(amount) || amount <= 0) {
      setError('Please specify a valid approved quota amount.');
      return;
    }

    setApproving(true);
    setError('');
    try {
      const payload: QuotaRequestReviewPayload = {
        action: 'approve',
        approved_quota_usd: amount,
        approved_duration: approvedDuration,
        admin_note: approvalNote.trim() || undefined,
      };

      if (propOnApprove) {
        await propOnApprove(selectedRequestForApproval.request_id, payload);
      } else {
        await reviewQuotaRequest(selectedRequestForApproval.request_id, payload);
        await loadRequests();
      }

      setSuccessMessage(
        `Approved quota of $${amount.toFixed(2)}/wk for ${selectedRequestForApproval.user_email} (${
          approvedDuration === 'TEMPORARY_WEEKLY' ? 'Temporary' : 'Permanent'
        })`
      );
      setApprovalModalOpen(false);
      setSelectedRequestIds((prev) => prev.filter((id) => id !== selectedRequestForApproval.request_id));
    } catch (err: any) {
      setError(err.message || 'Failed to approve quota request.');
    } finally {
      setApproving(false);
    }
  };

  // Open Rejection Dialog
  const handleOpenRejectDialog = (req: QuotaRequest) => {
    setSelectedRequestForRejection(req);
    setRejectionReason('');
    setRejectionModalOpen(true);
  };

  // Confirm Single Rejection
  const handleConfirmRejection = async () => {
    if (!selectedRequestForRejection) return;
    if (!rejectionReason.trim()) {
      setError('A decline reason / admin note is required.');
      return;
    }

    setRejecting(true);
    setError('');
    try {
      const payload: QuotaRequestReviewPayload = {
        action: 'reject',
        admin_note: rejectionReason.trim(),
      };

      if (propOnReject) {
        await propOnReject(selectedRequestForRejection.request_id, payload);
      } else {
        await reviewQuotaRequest(selectedRequestForRejection.request_id, payload);
        await loadRequests();
      }

      setSuccessMessage(
        `Declined quota request for ${selectedRequestForRejection.user_email}. Developer placed on cooldown until next reset.`
      );
      setRejectionModalOpen(false);
      setSelectedRequestIds((prev) => prev.filter((id) => id !== selectedRequestForRejection.request_id));
    } catch (err: any) {
      setError(err.message || 'Failed to decline quota request.');
    } finally {
      setRejecting(false);
    }
  };

  // Confirm Bulk Approval
  const handleConfirmBulkApproval = async () => {
    if (selectedRequestIds.length === 0) return;
    setBulkApproving(true);
    setError('');
    try {
      const payload: QuotaRequestBulkReviewPayload = {
        request_ids: selectedRequestIds,
        action: 'approve',
        approved_duration: bulkDuration,
        admin_note: bulkNote.trim() || undefined,
      };

      if (propOnBulkApprove) {
        await propOnBulkApprove(payload);
      } else {
        await bulkReviewQuotaRequests(payload);
        await loadRequests();
      }

      setSuccessMessage(`Successfully bulk-approved ${selectedRequestIds.length} quota requests!`);
      setSelectedRequestIds([]);
      setBulkModalOpen(false);
    } catch (err: any) {
      setError(err.message || 'Failed to bulk-approve quota requests.');
    } finally {
      setBulkApproving(false);
    }
  };

  const paginatedRequests = filteredRequests.slice(
    page * rowsPerPage,
    page * rowsPerPage + rowsPerPage
  );

  return (
    <Box>
      {/* Top Banner Notifications */}
      {error && (
        <Alert severity="error" sx={{ mb: 2.5, borderRadius: 2 }} onClose={() => setError('')}>
          {error}
        </Alert>
      )}
      {successMessage && (
        <Alert severity="success" sx={{ mb: 2.5, borderRadius: 2 }} onClose={() => setSuccessMessage('')}>
          {successMessage}
        </Alert>
      )}

      {/* Header & Sub-Tabs Navigation */}
      <Paper
        elevation={0}
        sx={{
          borderRadius: 3,
          border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
          backgroundColor: isDark ? '#111827' : '#ffffff',
          mb: 3,
          overflow: 'hidden',
        }}
      >
        <Box
          sx={{
            p: { xs: 2, md: 2.5 },
            display: 'flex',
            flexDirection: { xs: 'column', md: 'row' },
            justifyContent: 'space-between',
            alignItems: { xs: 'flex-start', md: 'center' },
            gap: 2,
            borderBottom: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.06)' : '#f1f5f9'}`,
          }}
        >
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.1rem' }}>
                Quota Increase Requests
              </Typography>
              {pendingCount > 0 && (
                <Chip
                  label={`${pendingCount} pending`}
                  size="small"
                  sx={{
                    bgcolor: isDark ? 'rgba(245, 158, 11, 0.2)' : 'rgba(245, 158, 11, 0.12)',
                    color: '#f59e0b',
                    fontWeight: 700,
                    height: 22,
                    fontSize: '0.72rem',
                    border: '1px solid rgba(245, 158, 11, 0.3)',
                  }}
                />
              )}
            </Box>
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
              Review, approve sprint boosts, configure permanent overrides, and manage anti-spam cooldowns
            </Typography>
          </Box>

          <Stack direction="row" spacing={1.5} alignItems="center">
            {/* Bulk Approve Action Button */}
            {selectedRequestIds.length > 0 && (
              <Button
                variant="contained"
                size="small"
                startIcon={<DoneAllIcon />}
                onClick={() => {
                  setBulkDuration('TEMPORARY_WEEKLY');
                  setBulkNote('');
                  setBulkModalOpen(true);
                }}
                sx={{
                  bgcolor: '#10b981',
                  '&:hover': { bgcolor: '#059669' },
                  fontWeight: 600,
                  borderRadius: 2,
                }}
              >
                Bulk Approve Selected ({selectedRequestIds.length})
              </Button>
            )}

            <TextField
              size="small"
              placeholder="Search by email, justification..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              sx={{ width: { xs: '100%', sm: 260 } }}
            />

            <Tooltip title="Refresh Requests Queue">
              <IconButton size="small" onClick={loadRequests} disabled={isLoading}>
                <RefreshIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Stack>
        </Box>

        {/* Sub-Tabs: Pending, Approved, Rejected, All */}
        <Box sx={{ px: 2, bgcolor: isDark ? 'rgba(255, 255, 255, 0.01)' : '#f8fafc' }}>
          <Tabs
            value={activeTab}
            onChange={(_, val) => {
              setActiveTab(val);
              setSelectedRequestIds([]);
              setPage(0);
            }}
            textColor="primary"
            indicatorColor="primary"
            sx={{
              minHeight: 44,
              '& .MuiTab-root': {
                textTransform: 'none',
                fontWeight: 600,
                fontSize: '0.86rem',
                minHeight: 44,
                py: 1,
              },
            }}
          >
            <Tab value="PENDING" label={`Pending (${pendingCount})`} />
            <Tab value="APPROVED" label={`Approved (${approvedCount})`} />
            <Tab value="REJECTED" label={`Rejected (${rejectedCount})`} />
            <Tab value="ALL" label={`All Requests (${allCount})`} />
          </Tabs>
        </Box>
      </Paper>

      {/* Requests Table */}
      <TableContainer
        component={Paper}
        elevation={0}
        sx={{
          borderRadius: 3,
          border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
          backgroundColor: isDark ? '#111827' : '#ffffff',
          overflow: 'hidden',
        }}
      >
        <Table sx={{ minWidth: 850 }}>
          <TableHead>
            <TableRow>
              <TableCell padding="checkbox">
                <Checkbox
                  size="small"
                  indeterminate={
                    selectedRequestIds.length > 0 &&
                    selectedRequestIds.length < pendingRequestsInCurrentView.length
                  }
                  checked={allPendingSelected}
                  onChange={handleSelectAllToggle}
                  disabled={pendingRequestsInCurrentView.length === 0}
                />
              </TableCell>
              <TableCell>Developer</TableCell>
              <TableCell>Current Group & Spend</TableCell>
              <TableCell>Requested Quota & Tier</TableCell>
              <TableCell>Reason & Justification</TableCell>
              <TableCell>Submitted</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={8} align="center" sx={{ py: 6 }}>
                  <CircularProgress size={28} sx={{ mb: 1.5 }} />
                  <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                    Loading quota requests...
                  </Typography>
                </TableCell>
              </TableRow>
            ) : paginatedRequests.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} align="center" sx={{ py: 6 }}>
                  <HourglassEmptyIcon sx={{ fontSize: 36, color: 'text.secondary', mb: 1, opacity: 0.5 }} />
                  <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                    No requests found in this view
                  </Typography>
                  <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                    {searchQuery
                      ? 'No requests match your current search query.'
                      : activeTab === 'PENDING'
                      ? 'All pending quota requests have been reviewed!'
                      : 'No quota requests match the selected status filter.'}
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              paginatedRequests.map((req) => {
                const isSelected = selectedRequestIds.includes(req.request_id);
                const isPending = req.status === 'PENDING';
                const catDetails = getCategoryDetails(req.reason_category);
                const initials = req.user_email.split('@')[0].slice(0, 2).toUpperCase();

                return (
                  <TableRow
                    key={req.request_id}
                    hover
                    selected={isSelected}
                    sx={{
                      '&:last-child td, &:last-child th': { border: 0 },
                      bgcolor: isSelected
                        ? isDark
                          ? 'rgba(99, 102, 241, 0.08)'
                          : 'rgba(99, 102, 241, 0.04)'
                        : 'inherit',
                    }}
                  >
                    <TableCell padding="checkbox">
                      <Checkbox
                        size="small"
                        checked={isSelected}
                        disabled={!isPending}
                        onChange={() => handleToggleSelectRow(req.request_id)}
                      />
                    </TableCell>

                    {/* Developer Avatar & Email */}
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                        <Avatar
                          sx={{
                            width: 32,
                            height: 32,
                            fontSize: '0.75rem',
                            fontWeight: 700,
                            bgcolor: isDark ? 'rgba(99, 102, 241, 0.3)' : 'primary.light',
                            color: isDark ? 'primary.light' : '#ffffff',
                          }}
                        >
                          {initials}
                        </Avatar>
                        <Box>
                          <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.2 }}>
                            {req.user_email}
                          </Typography>
                          <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.7rem' }}>
                            ID: {req.request_id.slice(0, 8)}...
                          </Typography>
                        </Box>
                      </Box>
                    </TableCell>

                    {/* Current Group & Spend */}
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        ${req.current_spend_usd.toFixed(2)}
                      </Typography>
                      <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                        Limit: ${req.current_quota_usd.toFixed(2)}/wk ({req.current_group_id})
                      </Typography>
                    </TableCell>

                    {/* Requested Quota & Duration */}
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="body2" sx={{ fontWeight: 700, color: 'primary.main' }}>
                          ${req.requested_quota_usd.toFixed(2)}/wk
                        </Typography>
                        <Chip
                          size="small"
                          label={req.duration_needed === 'TEMPORARY_WEEKLY' ? 'Temporary' : 'Permanent'}
                          sx={{
                            height: 18,
                            fontSize: '0.66rem',
                            fontWeight: 600,
                            bgcolor:
                              req.duration_needed === 'TEMPORARY_WEEKLY'
                                ? 'rgba(99, 102, 241, 0.12)'
                                : 'rgba(16, 185, 129, 0.12)',
                            color: req.duration_needed === 'TEMPORARY_WEEKLY' ? 'primary.main' : '#10b981',
                          }}
                        />
                      </Box>
                      <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                        +{Math.max(0, req.requested_quota_usd - req.current_quota_usd).toFixed(2)} increase
                      </Typography>
                    </TableCell>

                    {/* Reason Category & Justification */}
                    <TableCell sx={{ maxWidth: 280 }}>
                      <Chip
                        size="small"
                        label={`${catDetails.icon} ${catDetails.label}`}
                        sx={{
                          height: 20,
                          fontSize: '0.68rem',
                          fontWeight: 600,
                          mb: 0.5,
                        }}
                      />
                      <Tooltip title={req.justification} arrow>
                        <Typography
                          variant="caption"
                          sx={{
                            display: '-webkit-box',
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: 'vertical',
                            overflow: 'hidden',
                            color: 'text.secondary',
                            lineHeight: 1.3,
                          }}
                        >
                          "{req.justification}"
                        </Typography>
                      </Tooltip>
                      {req.admin_note && (
                        <Typography
                          variant="caption"
                          sx={{
                            display: 'block',
                            color: isDark ? '#94a3b8' : '#475569',
                            fontStyle: 'italic',
                            mt: 0.5,
                          }}
                        >
                          Note: « {req.admin_note} »
                        </Typography>
                      )}
                    </TableCell>

                    {/* Submitted Timestamp */}
                    <TableCell>
                      <Tooltip title={new Date(req.created_at).toLocaleString()} arrow>
                        <Typography variant="caption" sx={{ fontWeight: 500, color: 'text.secondary' }}>
                          {formatRelativeTime(req.created_at)}
                        </Typography>
                      </Tooltip>
                    </TableCell>

                    {/* Status */}
                    <TableCell>{renderStatusChip(req.status)}</TableCell>

                    {/* Actions */}
                    <TableCell align="right">
                      {isPending ? (
                        <Stack direction="row" spacing={1} justifyContent="flex-end">
                          <Button
                            variant="contained"
                            size="small"
                            startIcon={<CheckIcon />}
                            onClick={() => handleOpenApproveDialog(req)}
                            sx={{
                              bgcolor: '#10b981',
                              '&:hover': { bgcolor: '#059669' },
                              fontWeight: 600,
                              fontSize: '0.75rem',
                              px: 1.5,
                              py: 0.4,
                              borderRadius: 1.5,
                            }}
                          >
                            Approve
                          </Button>
                          <Button
                            variant="outlined"
                            color="error"
                            size="small"
                            startIcon={<ClearIcon />}
                            onClick={() => handleOpenRejectDialog(req)}
                            sx={{
                              fontWeight: 600,
                              fontSize: '0.75rem',
                              px: 1.5,
                              py: 0.4,
                              borderRadius: 1.5,
                            }}
                          >
                            Reject
                          </Button>
                        </Stack>
                      ) : (
                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                          {req.reviewed_by ? `By ${req.reviewed_by}` : 'Closed'}
                        </Typography>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>

        {/* Pagination */}
        <TablePagination
          component="div"
          count={filteredRequests.length}
          page={page}
          onPageChange={(_, newPage) => setPage(newPage)}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={(e) => {
            setRowsPerPage(parseInt(e.target.value, 10));
            setPage(0);
          }}
          rowsPerPageOptions={[5, 10, 25]}
        />
      </TableContainer>

      {/* ================= Approval Dialog with Flexibility ================= */}
      <Dialog
        open={approvalModalOpen}
        onClose={() => !approving && setApprovalModalOpen(false)}
        maxWidth="xs"
        fullWidth
        PaperProps={{ sx: { borderRadius: 3 } }}
      >
        <DialogTitle sx={{ pb: 1, borderBottom: '1px solid', borderColor: 'divider' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <CheckCircleIcon sx={{ color: '#10b981' }} />
              <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.05rem' }}>
                Approve Quota Increase Request
              </Typography>
            </Box>
            <IconButton size="small" onClick={() => setApprovalModalOpen(false)} disabled={approving}>
              <CloseIcon fontSize="small" />
            </IconButton>
          </Box>
        </DialogTitle>

        <DialogContent sx={{ pt: 2.5, pb: 1.5 }}>
          {selectedRequestForApproval && (
            <Stack spacing={2.5}>
              <Paper
                variant="outlined"
                sx={{
                  p: 1.75,
                  borderRadius: 2,
                  bgcolor: isDark ? 'rgba(255, 255, 255, 0.02)' : '#f8fafc',
                }}
              >
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block' }}>
                  DEVELOPER
                </Typography>
                <Typography variant="body2" sx={{ fontWeight: 700 }}>
                  {selectedRequestForApproval.user_email}
                </Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mt: 0.5 }}>
                  Requested: <strong>${selectedRequestForApproval.requested_quota_usd.toFixed(2)}/wk</strong> (Current:{' '}
                  ${selectedRequestForApproval.current_quota_usd.toFixed(2)}/wk)
                </Typography>
              </Paper>

              {/* Editable Approved Quota */}
              <TextField
                fullWidth
                size="small"
                type="number"
                label="Approved Weekly Quota ($)"
                value={approvedAmount}
                onChange={(e) => setApprovedAmount(e.target.value)}
                InputProps={{
                  startAdornment: <InputAdornment position="start">$</InputAdornment>,
                  endAdornment: <InputAdornment position="end">/week</InputAdornment>,
                }}
                helperText="Admins can grant the exact requested amount or adjust as needed."
              />

              {/* Duration Flexibility: Temporary vs Permanent */}
              <Box>
                <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                  Approval Duration
                </Typography>
                <RadioGroup
                  value={approvedDuration}
                  onChange={(e) => setApprovedDuration(e.target.value as QuotaRequestDuration)}
                  sx={{ gap: 1 }}
                >
                  <Paper
                    variant="outlined"
                    sx={{
                      p: 1.25,
                      borderRadius: 2,
                      borderColor: approvedDuration === 'TEMPORARY_WEEKLY' ? '#10b981' : 'divider',
                      bgcolor: approvedDuration === 'TEMPORARY_WEEKLY' ? 'rgba(16, 185, 129, 0.06)' : 'transparent',
                    }}
                  >
                    <FormControlLabel
                      value="TEMPORARY_WEEKLY"
                      control={<Radio size="small" color="secondary" />}
                      label={
                        <Box>
                          <Typography variant="body2" sx={{ fontWeight: 600 }}>
                            Temporary — Current Week Only
                          </Typography>
                          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                            Automatically reverts to group baseline at upcoming weekly Cloud Monitoring reset
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
                      borderColor: approvedDuration === 'PERMANENT' ? '#10b981' : 'divider',
                      bgcolor: approvedDuration === 'PERMANENT' ? 'rgba(16, 185, 129, 0.06)' : 'transparent',
                    }}
                  >
                    <FormControlLabel
                      value="PERMANENT"
                      control={<Radio size="small" color="secondary" />}
                      label={
                        <Box>
                          <Typography variant="body2" sx={{ fontWeight: 600 }}>
                            Permanent Override
                          </Typography>
                          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                            Sets a persistent custom quota that carries forward across future weekly resets
                          </Typography>
                        </Box>
                      }
                      sx={{ m: 0, width: '100%' }}
                    />
                  </Paper>
                </RadioGroup>
              </Box>

              {/* Optional Admin Note */}
              <TextField
                fullWidth
                size="small"
                multiline
                rows={2}
                label="Admin Note (Optional)"
                placeholder="e.g. Approved for sprint 42 load tests; please use Flash models where possible."
                value={approvalNote}
                onChange={(e) => setApprovalNote(e.target.value)}
              />
            </Stack>
          )}
        </DialogContent>

        <DialogActions sx={{ px: 3, py: 2, borderTop: '1px solid', borderColor: 'divider' }}>
          <Button onClick={() => setApprovalModalOpen(false)} disabled={approving}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={handleConfirmApproval}
            disabled={approving}
            sx={{
              bgcolor: '#10b981',
              '&:hover': { bgcolor: '#059669' },
              fontWeight: 600,
            }}
          >
            {approving ? 'Applying...' : 'Approve & Apply'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ================= Rejection Dialog with Cooldown Warning ================= */}
      <Dialog
        open={rejectionModalOpen}
        onClose={() => !rejecting && setRejectionModalOpen(false)}
        maxWidth="xs"
        fullWidth
        PaperProps={{ sx: { borderRadius: 3 } }}
      >
        <DialogTitle sx={{ pb: 1, borderBottom: '1px solid', borderColor: 'divider' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <CancelIcon sx={{ color: '#ef4444' }} />
              <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.05rem' }}>
                Decline Quota Increase Request
              </Typography>
            </Box>
            <IconButton size="small" onClick={() => setRejectionModalOpen(false)} disabled={rejecting}>
              <CloseIcon fontSize="small" />
            </IconButton>
          </Box>
        </DialogTitle>

        <DialogContent sx={{ pt: 2.5, pb: 1.5 }}>
          {selectedRequestForRejection && (
            <Stack spacing={2.5}>
              <Alert severity="warning" sx={{ borderRadius: 2 }}>
                Declining this request will place <strong>{selectedRequestForRejection.user_email}</strong> on
                anti-spam cooldown until the next weekly Cloud Monitoring reset.
              </Alert>

              <TextField
                fullWidth
                required
                multiline
                rows={3}
                label="Decline Reason / Admin Note"
                placeholder="e.g. Current sprint burn rate is within standard capacity; please switch to Gemini Flash for test generation."
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                helperText="This explanation is visible to the developer on their self-service dashboard."
              />
            </Stack>
          )}
        </DialogContent>

        <DialogActions sx={{ px: 3, py: 2, borderTop: '1px solid', borderColor: 'divider' }}>
          <Button onClick={() => setRejectionModalOpen(false)} disabled={rejecting}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color="error"
            onClick={handleConfirmRejection}
            disabled={rejecting || !rejectionReason.trim()}
            sx={{ fontWeight: 600 }}
          >
            {rejecting ? 'Declining...' : 'Decline Request'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ================= Bulk Approval Dialog ================= */}
      <Dialog
        open={bulkModalOpen}
        onClose={() => !bulkApproving && setBulkModalOpen(false)}
        maxWidth="xs"
        fullWidth
        PaperProps={{ sx: { borderRadius: 3 } }}
      >
        <DialogTitle sx={{ pb: 1, borderBottom: '1px solid', borderColor: 'divider' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <DoneAllIcon sx={{ color: '#10b981' }} />
              <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.05rem' }}>
                Bulk Approve ({selectedRequestIds.length}) Requests
              </Typography>
            </Box>
            <IconButton size="small" onClick={() => setBulkModalOpen(false)} disabled={bulkApproving}>
              <CloseIcon fontSize="small" />
            </IconButton>
          </Box>
        </DialogTitle>

        <DialogContent sx={{ pt: 2.5, pb: 1.5 }}>
          <Stack spacing={2.5}>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              You are approving <strong>{selectedRequestIds.length}</strong> selected developer quota requests at their
              full requested limits.
            </Typography>

            <Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                Duration for Selected Requests
              </Typography>
              <RadioGroup
                value={bulkDuration}
                onChange={(e) => setBulkDuration(e.target.value as QuotaRequestDuration)}
                sx={{ gap: 1 }}
              >
                <Paper
                  variant="outlined"
                  sx={{
                    p: 1.25,
                    borderRadius: 2,
                    borderColor: bulkDuration === 'TEMPORARY_WEEKLY' ? '#10b981' : 'divider',
                  }}
                >
                  <FormControlLabel
                    value="TEMPORARY_WEEKLY"
                    control={<Radio size="small" color="secondary" />}
                    label={
                      <Box>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          Temporary (This week only)
                        </Typography>
                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                          Reverts to group baseline upon upcoming weekly reset
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
                    borderColor: bulkDuration === 'PERMANENT' ? '#10b981' : 'divider',
                  }}
                >
                  <FormControlLabel
                    value="PERMANENT"
                    control={<Radio size="small" color="secondary" />}
                    label={
                      <Box>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          Permanent Overrides
                        </Typography>
                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                          Carries forward across future weekly resets
                        </Typography>
                      </Box>
                    }
                    sx={{ m: 0, width: '100%' }}
                  />
                </Paper>
              </RadioGroup>
            </Box>

            <TextField
              fullWidth
              size="small"
              multiline
              rows={2}
              label="Admin Note (Optional)"
              placeholder="e.g. Bulk-approved for sprint milestone."
              value={bulkNote}
              onChange={(e) => setBulkNote(e.target.value)}
            />
          </Stack>
        </DialogContent>

        <DialogActions sx={{ px: 3, py: 2, borderTop: '1px solid', borderColor: 'divider' }}>
          <Button onClick={() => setBulkModalOpen(false)} disabled={bulkApproving}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={handleConfirmBulkApproval}
            disabled={bulkApproving}
            sx={{
              bgcolor: '#10b981',
              '&:hover': { bgcolor: '#059669' },
              fontWeight: 600,
            }}
          >
            {bulkApproving ? 'Approving...' : `Approve All (${selectedRequestIds.length})`}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
