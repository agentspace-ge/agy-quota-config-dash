import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  AppBar,
  Box,
  Button,
  ButtonGroup,
  Chip,
  CircularProgress,
  Container,
  CssBaseline,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Snackbar,
  Tab,
  Tabs,
  Toolbar,
  Tooltip,
  Typography,
} from '@mui/material';
import { ThemeProvider } from '@mui/material/styles';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import SyncIcon from '@mui/icons-material/Sync';
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined';
import PriceCheckOutlinedIcon from '@mui/icons-material/PriceCheckOutlined';
import HistoryOutlinedIcon from '@mui/icons-material/HistoryOutlined';
import RefreshIcon from '@mui/icons-material/Refresh';
import DarkModeOutlinedIcon from '@mui/icons-material/DarkModeOutlined';
import LightModeOutlinedIcon from '@mui/icons-material/LightModeOutlined';
import PersonAddOutlinedIcon from '@mui/icons-material/PersonAddOutlined';
import PeopleAltOutlinedIcon from '@mui/icons-material/PeopleAltOutlined';
import FolderSharedOutlinedIcon from '@mui/icons-material/FolderSharedOutlined';
import AssignmentOutlinedIcon from '@mui/icons-material/AssignmentOutlined';
import AdminPanelSettingsOutlinedIcon from '@mui/icons-material/AdminPanelSettingsOutlined';
import AccountCircleOutlinedIcon from '@mui/icons-material/AccountCircleOutlined';
import VisibilityOutlinedIcon from '@mui/icons-material/VisibilityOutlined';

import { getTheme } from './theme';
import { DisclaimerBanner } from './components/DisclaimerBanner';
import { KPISummary } from './components/KPISummary';
import { UserTable } from './components/UserTable';
import { GroupsTab } from './components/GroupsTab';
import { RequestsTab } from './components/RequestsTab';
import { SelfServiceCard } from './components/SelfServiceCard';
import { RequestQuotaModal } from './components/RequestQuotaModal';
import { UserDrawer } from './components/UserDrawer';
import { SettingsModal } from './components/SettingsModal';
import { PricingModal } from './components/PricingModal';
import { AuditModal } from './components/AuditModal';
import { AddUserModal } from './components/AddUserModal';

import {
  cancelQuotaRequest,
  createGroup,
  createQuotaRequest,
  createUser,
  deleteGroup,
  fetchConfig,
  fetchGroups,
  fetchKPIs,
  fetchMe,
  fetchPricing,
  fetchQuotaRequests,
  fetchUsers,
  publishAndSync,
  toggleUserLock,
  updateConfig,
  updateGroup,
  updatePricing,
  updateUser,
} from './services/api';
import {
  AppConfig,
  AuthMeResponse,
  KPIStats,
  ModelPricing,
  QuotaGroup,
  QuotaGroupCreateRequest,
  QuotaGroupUpdateRequest,
  QuotaRequest,
  QuotaRequestCreatePayload,
  User,
  UserUpdatePayload,
} from './types';

export const App: React.FC = () => {
  // Theme Mode State
  const [themeMode, setThemeMode] = useState<'dark' | 'light'>(() => {
    const params = new URLSearchParams(window.location.search);
    const themeParam = params.get('theme');
    if (themeParam === 'light' || themeParam === 'dark') return themeParam;
    const saved = localStorage.getItem('antigravity_theme_mode');
    if (saved === 'dark' || saved === 'light') return saved;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches
      ? 'light'
      : 'dark';
  });

  const activeTheme = useMemo(() => getTheme(themeMode), [themeMode]);

  const toggleThemeMode = () => {
    const next = themeMode === 'dark' ? 'light' : 'dark';
    setThemeMode(next);
    localStorage.setItem('antigravity_theme_mode', next);
  };

  useEffect(() => {
    const isDarkCurrent = themeMode === 'dark';
    document.body.style.backgroundColor = isDarkCurrent ? '#090d16' : '#f8fafc';
    document.body.style.color = isDarkCurrent ? '#f9fafb' : '#0f172a';
  }, [themeMode]);

  // Auth, Profile & View Mode State
  const [authMe, setAuthMe] = useState<AuthMeResponse | null>(null);
  const [viewMode, setViewMode] = useState<'admin' | 'developer'>(() => {
    const path = window.location.pathname.toLowerCase();
    const hash = window.location.hash.toLowerCase();
    if (path.includes('my-quota') || hash.includes('my-quota')) {
      return 'developer';
    }
    return 'admin';
  });
  const [impersonatedEmail, setImpersonatedEmail] = useState<string>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get('as_user') || '';
  });

  const [users, setUsers] = useState<User[]>([]);
  const [groups, setGroups] = useState<QuotaGroup[]>([]);
  const [quotaRequests, setQuotaRequests] = useState<QuotaRequest[]>([]);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [pricing, setPricing] = useState<Record<string, ModelPricing>>({});
  const [kpis, setKPIs] = useState<KPIStats | null>(null);

  // Tab & Filter Navigation (for Admin View)
  const [currentTab, setCurrentTab] = useState<'users' | 'groups' | 'requests'>(() => {
    const hash = window.location.hash.toLowerCase();
    if (hash.includes('requests')) return 'requests';
    if (hash.includes('groups')) return 'groups';
    return 'users';
  });
  const [selectedGroupFilter, setSelectedGroupFilter] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);

  // Modals & Drawer State
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [pricingOpen, setPricingOpen] = useState(false);
  const [auditOpen, setAuditOpen] = useState(false);
  const [addUserOpen, setAddUserOpen] = useState(false);
  const [requestModalOpen, setRequestModalOpen] = useState(false);

  // Snackbar Notification
  const [snackbar, setSnackbar] = useState<{
    open: boolean;
    message: string;
    severity: 'success' | 'info' | 'warning' | 'error';
  }>({
    open: false,
    message: '',
    severity: 'info',
  });

  const loadData = async (impersonateTarget?: string) => {
    try {
      const targetUser = impersonateTarget !== undefined ? impersonateTarget : impersonatedEmail;
      const [meData, usersData, configData, pricingData, kpisData, groupsData, requestsData] =
        await Promise.all([
          fetchMe(targetUser || undefined),
          fetchUsers(),
          fetchConfig(),
          fetchPricing(),
          fetchKPIs(),
          fetchGroups(),
          fetchQuotaRequests(),
        ]);

      setAuthMe(meData);
      setUsers(usersData);
      setConfig(configData);
      setPricing(pricingData);
      setKPIs(kpisData);
      setGroups(groupsData);
      setQuotaRequests(requestsData);

      // If user is not an admin, lock view mode to developer self-service
      if (!meData.is_admin) {
        setViewMode('developer');
      }
    } catch (err) {
      console.error('Failed to load portal data:', err);
      showNotification('Failed to connect to backend service', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    document.title =
      viewMode === 'developer' || !authMe?.is_admin
        ? 'Antigravity · My Quota'
        : 'Antigravity Admin Console';
  }, [viewMode, authMe]);

  const showNotification = (
    message: string,
    severity: 'success' | 'info' | 'warning' | 'error' = 'success'
  ) => {
    setSnackbar({ open: true, message, severity });
  };

  const handleSelectUser = (user: User) => {
    setSelectedUser(user);
    setDrawerOpen(true);
  };

  const handleSaveUser = async (email: string, payload: UserUpdatePayload) => {
    try {
      const updated = await updateUser(email, payload);
      setUsers((prev) => prev.map((u) => (u.email === updated.email ? updated : u)));
      setSelectedUser(updated);
      const [newKPIs, newGroups] = await Promise.all([fetchKPIs(), fetchGroups()]);
      setKPIs(newKPIs);
      setGroups(newGroups);
      showNotification(
        `Changes saved for ${email}. Click "Publish & Sync" to reconcile Cloud Identity groups.`,
        'info'
      );
    } catch (e: any) {
      showNotification(e.message || 'Error updating developer', 'error');
    }
  };

  const handleToggleLock = async (email: string) => {
    try {
      const updated = await toggleUserLock(email);
      setUsers((prev) => prev.map((u) => (u.email === updated.email ? updated : u)));
      const newKPIs = await fetchKPIs();
      setKPIs(newKPIs);
      showNotification(`Access status updated for ${email}`, 'success');
    } catch (e: any) {
      showNotification(e.message || 'Error changing access lock', 'error');
    }
  };

  const handleToggleExempt = async (user: User) => {
    await handleSaveUser(user.email, { is_exempt: !user.is_exempt });
  };

  const handleAddUser = async (payload: {
    email: string;
    group_id?: string | null;
    is_exempt?: boolean;
    has_custom_quota?: boolean;
    custom_quota_usd?: number | null;
    custom_overage_usd?: number | null;
  }) => {
    const created = await createUser(payload);
    setUsers((prev) => [created, ...prev]);
    const [newKPIs, newGroups] = await Promise.all([fetchKPIs(), fetchGroups()]);
    setKPIs(newKPIs);
    setGroups(newGroups);
    showNotification(`Developer ${created.email} pre-provisioned successfully!`, 'success');
  };

  const handleCreateGroup = async (payload: QuotaGroupCreateRequest) => {
    try {
      const created = await createGroup(payload);
      setGroups((prev) => [...prev, created]);
      showNotification(`Quota group "${created.display_name}" created successfully.`, 'success');
    } catch (e: any) {
      showNotification(e.message || 'Failed to create quota group', 'error');
      throw e;
    }
  };

  const handleUpdateGroup = async (groupId: string, payload: QuotaGroupUpdateRequest) => {
    try {
      const updated = await updateGroup(groupId, payload);
      setGroups((prev) => prev.map((g) => (g.group_id === groupId ? updated : g)));
      const [newKPIs, newUsers] = await Promise.all([fetchKPIs(), fetchUsers()]);
      setKPIs(newKPIs);
      setUsers(newUsers);
      showNotification(`Quota group "${updated.display_name}" updated successfully.`, 'success');
    } catch (e: any) {
      showNotification(e.message || 'Failed to update quota group', 'error');
      throw e;
    }
  };

  const handleDeleteGroup = async (groupId: string) => {
    try {
      await deleteGroup(groupId);
      setGroups((prev) => prev.filter((g) => g.group_id !== groupId));
      if (selectedGroupFilter === groupId) {
        setSelectedGroupFilter(null);
      }
      const [newKPIs, newUsers] = await Promise.all([fetchKPIs(), fetchUsers()]);
      setKPIs(newKPIs);
      setUsers(newUsers);
      showNotification(`Quota group "${groupId}" deleted and members reassigned.`, 'info');
    } catch (e: any) {
      showNotification(e.message || 'Failed to delete quota group', 'error');
      throw e;
    }
  };

  const handleViewMembers = (groupId: string) => {
    setSelectedGroupFilter(groupId);
    setCurrentTab('users');
  };

  const handlePublishAndSync = async () => {
    setSyncing(true);
    try {
      const result = await publishAndSync();
      if (result.success) {
        showNotification(
          `Sync complete: ${result.users_evaluated} developers evaluated, ${result.group_swaps_count} group swaps executed.`,
          'success'
        );
        await loadData();
      } else {
        showNotification(`Sync evaluation failed: ${result.error}`, 'error');
      }
    } catch (e: any) {
      showNotification(e.message || 'Error during publish & sync', 'error');
    } finally {
      setSyncing(false);
    }
  };

  const handleSaveConfig = async (newConfig: Partial<AppConfig>) => {
    try {
      const updated = await updateConfig(newConfig);
      setConfig(updated);
      showNotification('Portal governance settings updated successfully', 'success');
    } catch (e: any) {
      showNotification(e.message || 'Failed to save configuration', 'error');
    }
  };

  const handleSavePricing = async (newPricing: Record<string, ModelPricing>) => {
    try {
      const updated = await updatePricing(newPricing);
      setPricing(updated);
      const newKPIs = await fetchKPIs();
      setKPIs(newKPIs);
      showNotification('Model pricing matrix updated successfully', 'success');
    } catch (e: any) {
      showNotification(e.message || 'Failed to save model pricing', 'error');
    }
  };

  // Developer Quota Request Submissions
  const handleSubmitQuotaRequest = async (payload: QuotaRequestCreatePayload) => {
    try {
      const created = await createQuotaRequest(payload);
      showNotification(
        `Quota increase request for $${created.requested_quota_usd.toFixed(2)}/wk submitted for admin review.`,
        'success'
      );
      setRequestModalOpen(false);
      await loadData();
    } catch (e: any) {
      showNotification(e.message || 'Failed to submit quota request', 'error');
      throw e;
    }
  };

  const handleCancelQuotaRequest = async (requestId: string) => {
    try {
      await cancelQuotaRequest(requestId);
      showNotification('Quota request successfully withdrawn.', 'info');
      await loadData();
    } catch (e: any) {
      showNotification(e.message || 'Failed to withdraw quota request', 'error');
      throw e;
    }
  };

  const handleImpersonateChange = async (targetEmail: string) => {
    setImpersonatedEmail(targetEmail);
    setLoading(true);
    await loadData(targetEmail);
    if (targetEmail) {
      setViewMode('developer');
    }
  };

  const isDark = activeTheme.palette.mode === 'dark';
  const pendingRequestsCount = useMemo(
    () => quotaRequests.filter((r) => r.status === 'PENDING').length,
    [quotaRequests]
  );

  const isDeveloperPortal = viewMode === 'developer' || !authMe?.is_admin;
  const portalTitle = isDeveloperPortal ? 'Antigravity' : 'Antigravity Admin Console';
  const portalSubtitle = isDeveloperPortal
    ? 'Personal usage, quota allowances, and access status'
    : 'Organization usage limits, directory access, and spend governance';

  return (
    <ThemeProvider theme={activeTheme}>
      <CssBaseline />
      <Box
        sx={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          bgcolor: 'background.default',
          color: 'text.primary',
          transition: 'background-color 0.2s ease, color 0.2s ease',
        }}
      >
        {/* Top Navigation Bar */}
        <AppBar
          position="sticky"
          elevation={0}
          sx={{
            borderBottom: 1,
            borderColor: isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.08)',
            backgroundColor: isDark ? 'rgba(18, 18, 18, 0.95)' : 'rgba(255, 255, 255, 0.95)',
            backdropFilter: 'blur(10px)',
          }}
        >
          <Toolbar sx={{ justifyContent: 'space-between', gap: 2 }}>
            {/* Brand Logo & Title */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: 38,
                  height: 38,
                  borderRadius: 2,
                  background: 'linear-gradient(135deg, #6366f1 0%, #3b82f6 50%, #06b6d4 100%)',
                  boxShadow: '0 2px 8px rgba(99, 102, 241, 0.35)',
                }}
              >
                <AutoAwesomeIcon sx={{ color: '#fff', fontSize: 20 }} />
              </Box>

              <Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Typography
                    variant="h6"
                    component="h1"
                    sx={{
                      fontWeight: 700,
                      letterSpacing: '-0.02em',
                      background: isDark
                        ? 'linear-gradient(90deg, #f8fafc 0%, #cbd5e1 100%)'
                        : 'linear-gradient(90deg, #0f172a 0%, #334155 100%)',
                      WebkitBackgroundClip: 'text',
                      WebkitTextFillColor: 'transparent',
                      lineHeight: 1.2,
                      fontSize: '1.15rem',
                    }}
                  >
                    {portalTitle}
                  </Typography>

                  <Chip
                    size="small"
                    label={config?.mock_mode ? 'MOCK MODE' : 'GCP CLOUD'}
                    color={config?.mock_mode ? 'warning' : 'success'}
                    variant="outlined"
                    sx={{
                      height: 20,
                      fontSize: '0.65rem',
                      fontWeight: 700,
                      letterSpacing: '0.04em',
                      borderColor: config?.mock_mode ? 'warning.main' : 'success.main',
                    }}
                  />
                </Box>
                <Typography
                  variant="caption"
                  sx={{ color: isDark ? '#6b7280' : '#94a3b8', fontSize: '0.72rem', display: 'block' }}
                >
                  {portalSubtitle}
                </Typography>
              </Box>
            </Box>

            {/* View Mode Switcher (Admin vs Developer) */}
            {authMe?.is_admin && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                <ButtonGroup
                  size="small"
                  variant="outlined"
                  sx={{
                    borderRadius: 2,
                    '& .MuiButton-root': {
                      px: 1.5,
                      py: 0.5,
                      textTransform: 'none',
                      fontWeight: 600,
                      fontSize: '0.8rem',
                    },
                  }}
                >
                  <Button
                    variant={viewMode === 'admin' ? 'contained' : 'outlined'}
                    startIcon={<AdminPanelSettingsOutlinedIcon fontSize="small" />}
                    onClick={() => {
                      setViewMode('admin');
                      setImpersonatedEmail('');
                    }}
                  >
                    Admin Console
                  </Button>
                  <Button
                    variant={viewMode === 'developer' ? 'contained' : 'outlined'}
                    startIcon={<AccountCircleOutlinedIcon fontSize="small" />}
                    onClick={() => setViewMode('developer')}
                  >
                    My Quota
                  </Button>
                </ButtonGroup>

                {/* Developer Preview Selector (for Admin to test developer experience) */}
                <FormControl size="small" sx={{ minWidth: 210 }}>
                  <InputLabel id="preview-user-select-label" sx={{ fontSize: '0.75rem' }}>
                    Preview As User
                  </InputLabel>
                  <Select
                    labelId="preview-user-select-label"
                    value={impersonatedEmail}
                    label="Preview As User"
                    onChange={(e) => handleImpersonateChange(e.target.value)}
                    sx={{
                      height: 34,
                      fontSize: '0.78rem',
                      borderRadius: 2,
                    }}
                  >
                    <MenuItem value="">
                      <em>Default (Myself - {authMe?.caller_email})</em>
                    </MenuItem>
                    {users.map((u) => (
                      <MenuItem key={u.email} value={u.email}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <span>{u.email}</span>
                          {u.status === 'AUTO_DISABLED' && (
                            <Chip size="small" label="THROTTLED" color="error" sx={{ height: 16, fontSize: '0.6rem' }} />
                          )}
                        </Box>
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Box>
            )}

            {/* Action Bar */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Tooltip title="Refresh Dashboard Telemetry">
                <IconButton size="small" onClick={() => loadData()} disabled={loading} sx={{ color: isDark ? '#9ca3af' : '#64748b' }}>
                  <RefreshIcon fontSize="small" />
                </IconButton>
              </Tooltip>

              {authMe?.is_admin && (
                <>
                  <Tooltip title="View Audit Trail">
                    <IconButton size="small" onClick={() => setAuditOpen(true)} sx={{ color: isDark ? '#9ca3af' : '#64748b' }}>
                      <HistoryOutlinedIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>

                  <Tooltip title="Configure Model Pricing Matrix">
                    <IconButton size="small" onClick={() => setPricingOpen(true)} sx={{ color: isDark ? '#9ca3af' : '#64748b' }}>
                      <PriceCheckOutlinedIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>

                  <Tooltip title="Portal Governance Settings">
                    <IconButton size="small" onClick={() => setSettingsOpen(true)} sx={{ color: isDark ? '#9ca3af' : '#64748b' }}>
                      <SettingsOutlinedIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </>
              )}

              {/* Theme Toggle Button */}
              <Tooltip title={`Switch to ${isDark ? 'Light' : 'Dark'} Mode`}>
                <IconButton size="small" onClick={toggleThemeMode} sx={{ color: isDark ? '#f59e0b' : '#6366f1' }}>
                  {isDark ? <LightModeOutlinedIcon fontSize="small" /> : <DarkModeOutlinedIcon fontSize="small" />}
                </IconButton>
              </Tooltip>

              {/* Quick Add Developer (Admin Only) */}
              {authMe?.is_admin && (
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<PersonAddOutlinedIcon fontSize="small" />}
                  onClick={() => setAddUserOpen(true)}
                  sx={{
                    ml: 0.5,
                    borderRadius: 2,
                    fontSize: '0.78rem',
                    borderColor: isDark ? 'rgba(255, 255, 255, 0.15)' : '#cbd5e1',
                    color: isDark ? '#e5e7eb' : '#334155',
                    '&:hover': {
                      borderColor: '#6366f1',
                      backgroundColor: isDark ? 'rgba(99, 102, 241, 0.08)' : 'rgba(99, 102, 241, 0.04)',
                    },
                  }}
                >
                  Add User
                </Button>
              )}

              {/* Publish & Sync Button (Admin Only) */}
              {authMe?.is_admin && (
                <Button
                  variant="contained"
                  size="small"
                  startIcon={syncing ? <CircularProgress size={14} color="inherit" /> : <SyncIcon fontSize="small" />}
                  onClick={handlePublishAndSync}
                  disabled={syncing}
                  sx={{
                    borderRadius: 2,
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    px: 1.75,
                    backgroundColor: '#10b981',
                    '&:hover': { backgroundColor: '#059669' },
                  }}
                >
                  {syncing ? 'Syncing...' : 'Publish & Sync'}
                </Button>
              )}
            </Box>
          </Toolbar>
        </AppBar>

        {/* Main Content Area */}
        <Container maxWidth="xl" sx={{ py: 3, flexGrow: 1 }}>
          <DisclaimerBanner />

          {/* Impersonation Banner */}
          {impersonatedEmail && (
            <Alert
              severity="warning"
              icon={<VisibilityOutlinedIcon fontSize="inherit" />}
              action={
                <Button color="inherit" size="small" onClick={() => handleImpersonateChange('')}>
                  Exit Preview
                </Button>
              }
              sx={{ mb: 3, borderRadius: 2 }}
            >
              <strong>Admin Preview Active:</strong> You are currently viewing the Self-Service
              Portal as <strong>{impersonatedEmail}</strong>.
            </Alert>
          )}

          {/* View Mode Switching: Developer Self-Service vs Admin Portal */}
          {viewMode === 'developer' ? (
            <Box sx={{ maxWidth: 1000, mx: 'auto', mt: 1 }}>
              <SelfServiceCard
                authMe={authMe}
                onOpenRequestModal={() => setRequestModalOpen(true)}
                onCancelRequest={handleCancelQuotaRequest}
                loading={loading}
              />
            </Box>
          ) : (
            <>
              <KPISummary kpis={kpis} loading={loading} />

              {/* Admin Navigation Tabs: Users, Groups, and Requests */}
              <Box sx={{ borderBottom: 1, borderColor: isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0', mb: 3 }}>
                <Tabs
                  value={currentTab}
                  onChange={(_, val) => setCurrentTab(val)}
                  textColor="primary"
                  indicatorColor="primary"
                  sx={{
                    '& .MuiTab-root': {
                      textTransform: 'none',
                      fontWeight: 600,
                      fontSize: '0.95rem',
                      py: 1.5,
                      minHeight: 48,
                      color: isDark ? '#9ca3af' : '#64748b',
                      '&.Mui-selected': {
                        color: isDark ? '#818cf8' : '#4f46e5',
                      },
                    },
                  }}
                >
                  <Tab
                    value="users"
                    label={`Users (${users.length})`}
                    icon={<PeopleAltOutlinedIcon sx={{ fontSize: 19 }} />}
                    iconPosition="start"
                  />
                  <Tab
                    value="groups"
                    label={`Groups (${groups.length})`}
                    icon={<FolderSharedOutlinedIcon sx={{ fontSize: 19 }} />}
                    iconPosition="start"
                  />
                  <Tab
                    value="requests"
                    label={
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <span>Quota Increase Requests</span>
                        {pendingRequestsCount > 0 && (
                          <Chip
                            size="small"
                            label={`${pendingRequestsCount} Pending`}
                            color="warning"
                            sx={{ height: 20, fontSize: '0.7rem', fontWeight: 700 }}
                          />
                        )}
                      </Box>
                    }
                    icon={<AssignmentOutlinedIcon sx={{ fontSize: 19 }} />}
                    iconPosition="start"
                  />
                </Tabs>
              </Box>

              {/* Tab Content */}
              {currentTab === 'users' && (
                <UserTable
                  users={users}
                  groups={groups}
                  selectedGroupId={selectedGroupFilter}
                  onSelectGroupId={setSelectedGroupFilter}
                  nextResetUtc={kpis?.credit_pool?.next_reset_utc}
                  onSelectUser={handleSelectUser}
                  onToggleLock={handleToggleLock}
                  onToggleExempt={handleToggleExempt}
                  onOpenAddUser={() => setAddUserOpen(true)}
                />
              )}

              {currentTab === 'groups' && (
                <GroupsTab
                  groups={groups}
                  users={users}
                  loading={loading}
                  onRefresh={loadData}
                  onViewMembers={handleViewMembers}
                  onCreateGroup={handleCreateGroup}
                  onUpdateGroup={handleUpdateGroup}
                  onDeleteGroup={handleDeleteGroup}
                />
              )}

              {currentTab === 'requests' && (
                <RequestsTab
                  requests={quotaRequests}
                  loading={loading}
                  onRefresh={loadData}
                />
              )}
            </>
          )}
        </Container>

        {/* Developer Quota Request Modal */}
        <RequestQuotaModal
          open={requestModalOpen}
          onClose={() => setRequestModalOpen(false)}
          onSubmit={handleSubmitQuotaRequest}
          user={authMe?.user || null}
          group={authMe?.group || null}
        />

        {/* Admin Drawers & Modals */}
        <UserDrawer
          user={selectedUser}
          groups={groups}
          config={config}
          nextResetUtc={kpis?.credit_pool?.next_reset_utc}
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          onSave={handleSaveUser}
        />

        <SettingsModal
          config={config}
          open={settingsOpen}
          onClose={() => setSettingsOpen(false)}
          onSave={handleSaveConfig}
        />

        <PricingModal
          pricing={pricing}
          open={pricingOpen}
          onClose={() => setPricingOpen(false)}
          onSave={handleSavePricing}
        />

        <AuditModal open={auditOpen} onClose={() => setAuditOpen(false)} />

        <AddUserModal
          config={config}
          groups={groups}
          open={addUserOpen}
          onClose={() => setAddUserOpen(false)}
          onAdd={handleAddUser}
        />

        {/* Notifications */}
        <Snackbar
          open={snackbar.open}
          autoHideDuration={6000}
          onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        >
          <Alert
            onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
            severity={snackbar.severity}
            variant="filled"
            sx={{ width: '100%', fontWeight: 500 }}
          >
            {snackbar.message}
          </Alert>
        </Snackbar>
      </Box>
    </ThemeProvider>
  );
};

export default App;
