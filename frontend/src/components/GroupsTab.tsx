import React, { useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Grid,
  IconButton,
  InputAdornment,
  Switch,
  TextField,
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material';
import GroupAddOutlinedIcon from '@mui/icons-material/GroupAddOutlined';
import GroupsOutlinedIcon from '@mui/icons-material/GroupsOutlined';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import PeopleOutlineIcon from '@mui/icons-material/PeopleOutline';
import PersonAddAlt1OutlinedIcon from '@mui/icons-material/PersonAddAlt1Outlined';
import AttachMoneyIcon from '@mui/icons-material/AttachMoney';
import TokenIcon from '@mui/icons-material/Token';
import ShieldOutlinedIcon from '@mui/icons-material/ShieldOutlined';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import RefreshIcon from '@mui/icons-material/Refresh';
import { QuotaGroup, QuotaGroupCreateRequest, QuotaGroupUpdateRequest, User } from '../types';

interface GroupsTabProps {
  groups: QuotaGroup[];
  users?: User[];
  loading?: boolean;
  onRefresh?: () => void;
  onCreateGroup: (payload: QuotaGroupCreateRequest) => Promise<void>;
  onUpdateGroup: (groupId: string, payload: QuotaGroupUpdateRequest) => Promise<void>;
  onDeleteGroup: (groupId: string) => Promise<void>;
  onViewMembers: (groupId: string) => void;
}

export const GroupsTab: React.FC<GroupsTabProps> = ({
  groups,
  users,
  loading = false,
  onRefresh,
  onCreateGroup,
  onUpdateGroup,
  onDeleteGroup,
  onViewMembers,
}) => {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';

  // Create Dialog State
  const [createOpen, setCreateOpen] = useState(false);
  const [newGroupId, setNewGroupId] = useState('');
  const [newDisplayName, setNewDisplayName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newQuota, setNewQuota] = useState('25.00');
  const [newBuffer, setNewBuffer] = useState('5.00');
  const [newIsExempt, setNewIsExempt] = useState(false);
  const [newIamEmail, setNewIamEmail] = useState('');
  const [createSaving, setCreateSaving] = useState(false);
  const [createError, setCreateError] = useState('');

  // Edit Dialog State
  const [editGroup, setEditGroup] = useState<QuotaGroup | null>(null);
  const [editDisplayName, setEditDisplayName] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editQuota, setEditQuota] = useState('25.00');
  const [editBuffer, setEditBuffer] = useState('5.00');
  const [editIsExempt, setEditIsExempt] = useState(false);
  const [editIamEmail, setEditIamEmail] = useState('');
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState('');

  // Delete Dialog State
  const [deleteTarget, setDeleteTarget] = useState<QuotaGroup | null>(null);
  const [deleteSaving, setDeleteSaving] = useState(false);

  // Assign Members Dialog State
  const [assignGroup, setAssignGroup] = useState<QuotaGroup | null>(null);
  const [assignEmailsText, setAssignEmailsText] = useState('');
  const [assignResetCustom, setAssignResetCustom] = useState(true);
  const [assignSaving, setAssignSaving] = useState(false);
  const [assignError, setAssignError] = useState('');

  const handleOpenCreate = () => {
    setNewGroupId('');
    setNewDisplayName('');
    setNewDescription('');
    setNewQuota('25.00');
    setNewBuffer('5.00');
    setNewIsExempt(false);
    setNewIamEmail('');
    setCreateError('');
    setCreateOpen(true);
  };

  const handleSaveCreate = async () => {
    if (!newGroupId.trim() || !newDisplayName.trim()) {
      setCreateError('Group ID and Display Name are required.');
      return;
    }
    const slug = newGroupId.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '-');
    setCreateSaving(true);
    setCreateError('');
    try {
      await onCreateGroup({
        group_id: slug,
        display_name: newDisplayName.trim(),
        description: newDescription.trim(),
        weekly_quota_usd: parseFloat(newQuota) || 25.0,
        overage_buffer_usd: parseFloat(newBuffer) || 5.0,
        is_exempt: newIsExempt,
        iam_group_email: newIamEmail.trim() || undefined,
      });
      setCreateOpen(false);
    } catch (e: any) {
      setCreateError(e.message || 'Failed to create group');
    } finally {
      setCreateSaving(false);
    }
  };

  const handleOpenEdit = (group: QuotaGroup) => {
    setEditGroup(group);
    setEditDisplayName(group.display_name);
    setEditDescription(group.description || '');
    setEditQuota(group.weekly_quota_usd.toFixed(2));
    setEditBuffer(group.overage_buffer_usd.toFixed(2));
    setEditIsExempt(group.is_exempt);
    setEditIamEmail(group.iam_group_email || '');
    setEditError('');
  };

  const handleSaveEdit = async () => {
    if (!editGroup) return;
    setEditSaving(true);
    setEditError('');
    try {
      await onUpdateGroup(editGroup.group_id, {
        display_name: editDisplayName.trim(),
        description: editDescription.trim(),
        weekly_quota_usd: parseFloat(editQuota) || 25.0,
        overage_buffer_usd: parseFloat(editBuffer) || 5.0,
        is_exempt: editIsExempt,
        iam_group_email: editIamEmail.trim() || undefined,
      });
      setEditGroup(null);
    } catch (e: any) {
      setEditError(e.message || 'Failed to update group');
    } finally {
      setEditSaving(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleteSaving(true);
    try {
      await onDeleteGroup(deleteTarget.group_id);
      setDeleteTarget(null);
    } catch (e: any) {
      console.error(e);
    } finally {
      setDeleteSaving(false);
    }
  };

  const handleOpenAssign = (group: QuotaGroup) => {
    setAssignGroup(group);
    setAssignEmailsText('');
    setAssignResetCustom(true);
    setAssignError('');
  };

  const handleSaveAssign = async () => {
    if (!assignGroup) return;
    const emails = assignEmailsText
      .split(/[\n,]+/)
      .map((e) => e.trim().toLowerCase())
      .filter((e) => e.length > 0);

    if (emails.length === 0) {
      setAssignError('Please enter at least one developer email address.');
      return;
    }

    setAssignSaving(true);
    setAssignError('');
    try {
      const res = await fetch(`/api/groups/${assignGroup.group_id}/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          emails,
          action: 'add',
          reset_custom_quota: assignResetCustom,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to assign members');
      }
      setAssignGroup(null);
      if (onRefresh) onRefresh();
    } catch (err: any) {
      setAssignError(err.message || 'Error assigning members');
    } finally {
      setAssignSaving(false);
    }
  };

  return (
    <Box sx={{ mt: 2 }}>
      {/* Top Banner & Action */}
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          mb: 3,
          flexWrap: 'wrap',
          gap: 2,
        }}
      >
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.1rem' }}>
            Quota Management Groups
          </Typography>
          <Typography variant="body2" sx={{ color: isDark ? '#9ca3af' : '#64748b' }}>
            Configure baseline quotas, overage buffers, and exemptions applied automatically to all members.
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          {onRefresh && (
            <Tooltip title="Refresh Groups & Metrics">
              <IconButton
                size="small"
                onClick={onRefresh}
                disabled={loading}
                sx={{
                  border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.12)' : '#cbd5e1'}`,
                  borderRadius: 2,
                  p: 0.75,
                }}
              >
                {loading ? <CircularProgress size={16} color="inherit" /> : <RefreshIcon fontSize="small" />}
              </IconButton>
            </Tooltip>
          )}

          <Button
            variant="contained"
            size="small"
            startIcon={<GroupAddOutlinedIcon fontSize="small" />}
            onClick={handleOpenCreate}
            sx={{
              borderRadius: 2,
              px: 2,
              py: 0.75,
              fontSize: '0.82rem',
              fontWeight: 600,
              backgroundColor: '#6366f1',
              '&:hover': { backgroundColor: '#4f46e5' },
            }}
          >
            Create Quota Group
          </Button>
        </Box>
      </Box>

      {/* Groups Grid */}
      <Grid container spacing={2.5}>
        {groups.map((group) => {
          const isDefault = group.group_id === 'business-users';
          const isDev = group.group_id === 'developers';
          // Compute from direct API fields, with real-time fallback to users array and nested stats
          const groupUsers = users ? users.filter((u) => (u.group_id || 'business-users') === group.group_id) : [];
          const memberCount = group.member_count ?? group.stats?.member_count ?? groupUsers.length;
          const grossSpend = group.gross_spend_usd ?? group.stats?.gross_spend_usd ?? groupUsers.reduce((sum, u) => sum + (u.current_week?.gross_spend_usd || 0), 0);
          const totalTokens = group.total_tokens ?? group.stats?.total_tokens ?? groupUsers.reduce((sum, u) => sum + (u.current_week?.total_tokens || 0), 0);


          return (
            <Grid item xs={12} md={6} lg={4} key={group.group_id}>
              <Card
                variant="outlined"
                sx={{
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  borderRadius: 3,
                  borderColor: isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0',
                  backgroundColor: isDark ? 'rgba(17, 24, 39, 0.6)' : '#ffffff',
                  boxShadow: isDark ? '0 4px 20px rgba(0, 0, 0, 0.25)' : '0 2px 8px rgba(0, 0, 0, 0.04)',
                  transition: 'transform 0.15s ease, border-color 0.15s ease',
                  '&:hover': {
                    borderColor: isDark ? 'rgba(99, 102, 241, 0.4)' : '#a5b4fc',
                    transform: 'translateY(-2px)',
                  },
                }}
              >
                <CardContent sx={{ p: 2.5, flexGrow: 1 }}>
                  {/* Header Row */}
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1.5 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
                      <Box
                        sx={{
                          width: 38,
                          height: 38,
                          borderRadius: 2,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          backgroundColor: isDev
                            ? isDark
                              ? 'rgba(99, 102, 241, 0.2)'
                              : 'rgba(99, 102, 241, 0.1)'
                            : isDark
                            ? 'rgba(59, 130, 246, 0.2)'
                            : 'rgba(59, 130, 246, 0.1)',
                          color: isDev ? '#818cf8' : '#3b82f6',
                        }}
                      >
                        <GroupsOutlinedIcon fontSize="small" />
                      </Box>
                      <Box>
                        <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
                          {group.display_name}
                        </Typography>
                        <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b', fontFamily: 'monospace' }}>
                          @{group.group_id}
                        </Typography>
                      </Box>
                    </Box>

                    <Box sx={{ display: 'flex', gap: 0.5 }}>
                      {isDefault && (
                        <Chip
                          label="Default"
                          size="small"
                          sx={{
                            height: 22,
                            fontSize: '0.68rem',
                            fontWeight: 600,
                            backgroundColor: isDark ? 'rgba(156, 163, 175, 0.15)' : 'rgba(100, 116, 139, 0.1)',
                            color: isDark ? '#9ca3af' : '#475569',
                          }}
                        />
                      )}
                      {group.is_exempt && (
                        <Chip
                          label="Exempt"
                          size="small"
                          icon={<ShieldOutlinedIcon sx={{ fontSize: '12px !important', color: 'inherit !important' }} />}
                          sx={{
                            height: 22,
                            fontSize: '0.68rem',
                            fontWeight: 600,
                            backgroundColor: isDark ? 'rgba(99, 102, 241, 0.2)' : 'rgba(99, 102, 241, 0.1)',
                            color: isDark ? '#a5b4fc' : '#4f46e5',
                          }}
                        />
                      )}
                    </Box>
                  </Box>

                  {/* Description */}
                  <Typography
                    variant="body2"
                    sx={{
                      color: isDark ? '#9ca3af' : '#64748b',
                      fontSize: '0.82rem',
                      minHeight: 38,
                      mb: 2,
                    }}
                  >
                    {group.description || 'No description provided.'}
                  </Typography>

                  {/* Quota Specs */}
                  <Box
                    sx={{
                      display: 'flex',
                      gap: 2,
                      p: 1.5,
                      borderRadius: 2,
                      backgroundColor: isDark ? 'rgba(0, 0, 0, 0.25)' : '#f8fafc',
                      border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.04)' : '#edf2f7'}`,
                      mb: 2,
                    }}
                  >
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b', display: 'block' }}>
                        Weekly Quota
                      </Typography>
                      <Typography variant="h6" sx={{ fontWeight: 700, color: '#10b981', fontSize: '1.1rem' }}>
                        ${group.weekly_quota_usd.toFixed(2)}
                      </Typography>
                    </Box>
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b', display: 'block' }}>
                        Overage Buffer
                      </Typography>
                      <Typography variant="h6" sx={{ fontWeight: 700, color: '#f59e0b', fontSize: '1.1rem' }}>
                        +${group.overage_buffer_usd.toFixed(2)}
                      </Typography>
                    </Box>
                    <Box sx={{ flex: 1.2 }}>
                      <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b', display: 'block' }}>
                        Hard Cap
                      </Typography>
                      <Typography variant="h6" sx={{ fontWeight: 700, color: isDark ? '#f3f4f6' : '#1f2937', fontSize: '1.1rem' }}>
                        ${(group.weekly_quota_usd + group.overage_buffer_usd).toFixed(2)}
                      </Typography>
                    </Box>
                  </Box>

                  {/* Telemetry Metrics */}
                  <Grid container spacing={1}>
                    <Grid item xs={4}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                        <PeopleOutlineIcon sx={{ fontSize: 16, color: isDark ? '#9ca3af' : '#64748b' }} />
                        <Box>
                          <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b', display: 'block', fontSize: '0.7rem' }}>
                            Members
                          </Typography>
                          <Typography variant="body2" sx={{ fontWeight: 600 }}>
                            {memberCount}
                          </Typography>
                        </Box>
                      </Box>
                    </Grid>
                    <Grid item xs={4}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                        <AttachMoneyIcon sx={{ fontSize: 16, color: '#10b981' }} />
                        <Box>
                          <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b', display: 'block', fontSize: '0.7rem' }}>
                            Gross Spend
                          </Typography>
                          <Typography variant="body2" sx={{ fontWeight: 600 }}>
                            ${grossSpend.toFixed(2)}
                          </Typography>
                        </Box>
                      </Box>
                    </Grid>
                    <Grid item xs={4}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                        <TokenIcon sx={{ fontSize: 16, color: '#818cf8' }} />
                        <Box>
                          <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b', display: 'block', fontSize: '0.7rem' }}>
                            Tokens
                          </Typography>
                          <Typography variant="body2" sx={{ fontWeight: 600 }}>
                            {(totalTokens / 1_000_000).toFixed(2)}M
                          </Typography>
                        </Box>
                      </Box>
                    </Grid>
                  </Grid>

                  {group.iam_group_email && (
                    <Box sx={{ mt: 1.5, pt: 1.5, borderTop: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.06)' : '#f1f5f9'}` }}>
                      <Typography variant="caption" sx={{ color: isDark ? '#6b7280' : '#94a3b8', fontSize: '0.72rem' }}>
                        IAM Mapping: <span style={{ fontFamily: 'monospace' }}>{group.iam_group_email}</span>
                      </Typography>
                    </Box>
                  )}
                </CardContent>

                {/* Card Actions */}
                <CardActions
                  sx={{
                    px: 2.5,
                    py: 1.5,
                    borderTop: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.06)' : '#f1f5f9'}`,
                    justifyContent: 'space-between',
                  }}
                >
                  <Button
                    size="small"
                    endIcon={<ArrowForwardIcon fontSize="small" />}
                    onClick={() => onViewMembers(group.group_id)}
                    sx={{
                      fontSize: '0.78rem',
                      fontWeight: 600,
                      color: isDark ? '#a5b4fc' : '#4f46e5',
                    }}
                  >
                    View Members ({memberCount})
                  </Button>

                  <Box sx={{ display: 'flex', gap: 0.5 }}>
                    <Tooltip title={`Assign Members to ${group.display_name}`}>
                      <IconButton
                        size="small"
                        onClick={() => handleOpenAssign(group)}
                        sx={{ color: isDark ? '#9ca3af' : '#64748b' }}
                      >
                        <PersonAddAlt1OutlinedIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Edit Group Quota & Settings">
                      <IconButton size="small" onClick={() => handleOpenEdit(group)} sx={{ color: isDark ? '#9ca3af' : '#64748b' }}>
                        <EditOutlinedIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    {!isDefault && (
                      <Tooltip title="Delete Group (Reassigns members to Business Users)">
                        <IconButton
                          size="small"
                          onClick={() => setDeleteTarget(group)}
                          sx={{ color: isDark ? '#f87171' : '#ef4444' }}
                        >
                          <DeleteOutlineIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    )}
                  </Box>
                </CardActions>
              </Card>
            </Grid>
          );
        })}
      </Grid>

      {/* Create Group Dialog */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Create New Quota Group</DialogTitle>
        <DialogContent dividers>
          {createError && (
            <Typography variant="caption" sx={{ color: '#ef4444', display: 'block', mb: 2, fontWeight: 600 }}>
              {createError}
            </Typography>
          )}
          <Grid container spacing={2}>
            <Grid item xs={6}>
              <TextField
                fullWidth
                size="small"
                label="Group ID (slug)"
                placeholder="e.g. data-science"
                value={newGroupId}
                onChange={(e) => setNewGroupId(e.target.value)}
                helperText="Unique identifier"
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                fullWidth
                size="small"
                label="Display Name"
                placeholder="e.g. Data Science Team"
                value={newDisplayName}
                onChange={(e) => setNewDisplayName(e.target.value)}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                size="small"
                label="Description"
                placeholder="Target developers, purpose, or quota tier context"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                fullWidth
                size="small"
                label="Weekly Quota ($)"
                type="number"
                value={newQuota}
                onChange={(e) => setNewQuota(e.target.value)}
                InputProps={{ startAdornment: <InputAdornment position="start">$</InputAdornment> }}
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                fullWidth
                size="small"
                label="Overage Buffer ($)"
                type="number"
                value={newBuffer}
                onChange={(e) => setNewBuffer(e.target.value)}
                InputProps={{ startAdornment: <InputAdornment position="start">$</InputAdornment> }}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                size="small"
                label="IAM Group Email (Optional)"
                placeholder="e.g. agy-datascience@example.com"
                value={newIamEmail}
                onChange={(e) => setNewIamEmail(e.target.value)}
                helperText="Future Cloud Identity sync group binding"
              />
            </Grid>
            <Grid item xs={12}>
              <FormControlLabel
                control={
                  <Switch
                    checked={newIsExempt}
                    onChange={(e) => setNewIsExempt(e.target.checked)}
                    color="primary"
                  />
                }
                label="Exempt all members in this group from automated throttling"
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions sx={{ px: 3, py: 2 }}>
          <Button onClick={() => setCreateOpen(false)} disabled={createSaving}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={handleSaveCreate}
            disabled={createSaving}
            sx={{ backgroundColor: '#6366f1', '&:hover': { backgroundColor: '#4f46e5' } }}
          >
            {createSaving ? 'Creating...' : 'Create Group'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Edit Group Dialog */}
      <Dialog open={Boolean(editGroup)} onClose={() => setEditGroup(null)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>
          Edit Quota Group: {editGroup?.display_name}
        </DialogTitle>
        <DialogContent dividers>
          {editError && (
            <Typography variant="caption" sx={{ color: '#ef4444', display: 'block', mb: 2, fontWeight: 600 }}>
              {editError}
            </Typography>
          )}
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                size="small"
                label="Display Name"
                value={editDisplayName}
                onChange={(e) => setEditDisplayName(e.target.value)}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                size="small"
                label="Description"
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                fullWidth
                size="small"
                label="Weekly Quota ($)"
                type="number"
                value={editQuota}
                onChange={(e) => setEditQuota(e.target.value)}
                InputProps={{ startAdornment: <InputAdornment position="start">$</InputAdornment> }}
                helperText="Propagates to all non-custom members"
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                fullWidth
                size="small"
                label="Overage Buffer ($)"
                type="number"
                value={editBuffer}
                onChange={(e) => setNewBuffer(e.target.value)}
                InputProps={{ startAdornment: <InputAdornment position="start">$</InputAdornment> }}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                size="small"
                label="IAM Group Email (Optional)"
                value={editIamEmail}
                onChange={(e) => setEditIamEmail(e.target.value)}
              />
            </Grid>
            <Grid item xs={12}>
              <FormControlLabel
                control={
                  <Switch
                    checked={editIsExempt}
                    onChange={(e) => setEditIsExempt(e.target.checked)}
                    color="primary"
                  />
                }
                label="Exempt all members from automated throttling"
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions sx={{ px: 3, py: 2 }}>
          <Button onClick={() => setEditGroup(null)} disabled={editSaving}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={handleSaveEdit}
            disabled={editSaving}
            sx={{ backgroundColor: '#6366f1', '&:hover': { backgroundColor: '#4f46e5' } }}
          >
            {editSaving ? 'Saving...' : 'Save Group'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={Boolean(deleteTarget)} onClose={() => setDeleteTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700, color: '#ef4444' }}>Delete Quota Group?</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2" sx={{ mb: 1.5 }}>
            Are you sure you want to delete <strong>{deleteTarget?.display_name}</strong> (
            <code>{deleteTarget?.group_id}</code>)?
          </Typography>
          <Typography variant="body2" sx={{ color: isDark ? '#9ca3af' : '#64748b' }}>
            All existing members of this group will be automatically reassigned to the default{' '}
            <strong>Business Users</strong> group.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, py: 2 }}>
          <Button onClick={() => setDeleteTarget(null)} disabled={deleteSaving}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color="error"
            onClick={handleConfirmDelete}
            disabled={deleteSaving}
          >
            {deleteSaving ? 'Deleting...' : 'Delete Group'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Assign Members Dialog */}
      <Dialog open={Boolean(assignGroup)} onClose={() => setAssignGroup(null)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>
          Assign Members to {assignGroup?.display_name}
        </DialogTitle>
        <DialogContent dividers>
          {assignError && (
            <Typography variant="caption" sx={{ color: '#ef4444', display: 'block', mb: 2, fontWeight: 600 }}>
              {assignError}
            </Typography>
          )}

          <Typography variant="body2" sx={{ mb: 1.5, color: isDark ? '#9ca3af' : '#64748b' }}>
            Enter developer email addresses to assign or move to <strong>{assignGroup?.display_name}</strong> (quota: ${assignGroup?.weekly_quota_usd.toFixed(2)}/wk).
          </Typography>

          <TextField
            fullWidth
            multiline
            rows={4}
            size="small"
            placeholder="developer1@example.com&#10;developer2@example.com"
            value={assignEmailsText}
            onChange={(e) => setAssignEmailsText(e.target.value)}
            helperText="Enter one email per line, or separate with commas"
            sx={{ mb: 2 }}
          />

          <Box
            sx={{
              p: 1.5,
              borderRadius: 2,
              backgroundColor: isDark ? 'rgba(99, 102, 241, 0.08)' : '#eff6ff',
              border: `1px solid ${isDark ? 'rgba(99, 102, 241, 0.2)' : '#bfdbfe'}`,
            }}
          >
            <FormControlLabel
              control={
                <Checkbox
                  checked={assignResetCustom}
                  onChange={(e) => setAssignResetCustom(e.target.checked)}
                  color="primary"
                />
              }
              label={
                <Box>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    Reset custom quota overrides to group baseline (${assignGroup?.weekly_quota_usd.toFixed(2)}/wk)
                  </Typography>
                  <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b' }}>
                    Recommended. Automatically removes legacy custom limits so developers cleanly adopt {assignGroup?.display_name} quota.
                  </Typography>
                </Box>
              }
              sx={{ alignItems: 'flex-start', ml: 0 }}
            />
          </Box>
        </DialogContent>
        <DialogActions sx={{ px: 3, py: 2 }}>
          <Button onClick={() => setAssignGroup(null)} disabled={assignSaving}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={handleSaveAssign}
            disabled={assignSaving}
            sx={{ backgroundColor: '#6366f1', '&:hover': { backgroundColor: '#4f46e5' } }}
          >
            {assignSaving ? 'Assigning...' : 'Assign Members'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
