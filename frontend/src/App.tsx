import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  AppBar,
  Box,
  Button,
  CircularProgress,
  Container,
  CssBaseline,
  IconButton,
  Snackbar,
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

import { getTheme } from './theme';
import { DisclaimerBanner } from './components/DisclaimerBanner';
import { KPISummary } from './components/KPISummary';
import { UserTable } from './components/UserTable';
import { UserDrawer } from './components/UserDrawer';
import { SettingsModal } from './components/SettingsModal';
import { PricingModal } from './components/PricingModal';
import { AuditModal } from './components/AuditModal';
import { AddUserModal } from './components/AddUserModal';

import {
  createUser,
  fetchConfig,
  fetchKPIs,
  fetchPricing,
  fetchUsers,
  publishAndSync,
  toggleUserLock,
  updateConfig,
  updatePricing,
  updateUser,
} from './services/api';
import { AppConfig, KPIStats, ModelPricing, User, UserUpdatePayload } from './types';

export const App: React.FC = () => {
  // Theme Mode State
  const [themeMode, setThemeMode] = useState<'dark' | 'light'>(() => {
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

  const [users, setUsers] = useState<User[]>([]);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [pricing, setPricing] = useState<Record<string, ModelPricing>>({});
  const [kpis, setKPIs] = useState<KPIStats | null>(null);

  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);

  // Modals & Drawer State
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [pricingOpen, setPricingOpen] = useState(false);
  const [auditOpen, setAuditOpen] = useState(false);
  const [addUserOpen, setAddUserOpen] = useState(false);

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

  const loadData = async () => {
    try {
      const [usersData, configData, pricingData, kpisData] = await Promise.all([
        fetchUsers(),
        fetchConfig(),
        fetchPricing(),
        fetchKPIs(),
      ]);
      setUsers(usersData);
      setConfig(configData);
      setPricing(pricingData);
      setKPIs(kpisData);
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
      const newKPIs = await fetchKPIs();
      setKPIs(newKPIs);
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
    is_exempt?: boolean;
    has_custom_quota?: boolean;
    custom_quota_usd?: number | null;
    custom_overage_usd?: number | null;
  }) => {
    const created = await createUser(payload);
    setUsers((prev) => [created, ...prev]);
    const newKPIs = await fetchKPIs();
    setKPIs(newKPIs);
    showNotification(`Developer ${created.email} pre-provisioned successfully!`, 'success');
  };

  const handleSaveConfig = async (payload: Partial<AppConfig>) => {
    const updated = await updateConfig(payload);
    setConfig(updated);
    showNotification('Portal settings updated successfully.', 'success');
  };

  const handleSavePricing = async (matrix: Record<string, ModelPricing>) => {
    const updated = await updatePricing(matrix);
    setPricing(updated);
    showNotification('Model pricing matrix updated successfully.', 'success');
  };

  const handlePublishAndSync = async () => {
    setSyncing(true);
    try {
      const result = await publishAndSync();
      if (result.success) {
        showNotification(
          `Publish & Sync complete: ${result.users_evaluated} developers evaluated, ${result.group_swaps_count} group updates applied.`,
          'success'
        );
        await loadData();
      } else {
        showNotification(result.error || 'Evaluation error during sync', 'error');
      }
    } catch (e: any) {
      showNotification(e.message || 'Failed to trigger publish & sync', 'error');
    } finally {
      setSyncing(false);
    }
  };

  const isDark = themeMode === 'dark';

  return (
    <ThemeProvider theme={activeTheme}>
      <CssBaseline />
      <Box
        sx={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          bgcolor: 'background.default',
        }}
      >
        {/* Translucent Glassmorphism Header */}
        <AppBar
          position="sticky"
          elevation={0}
          sx={{
            backdropFilter: 'blur(16px)',
            backgroundColor: isDark ? 'rgba(9, 13, 22, 0.85)' : 'rgba(255, 255, 255, 0.85)',
            borderBottom: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
            color: 'text.primary',
            zIndex: (theme) => theme.zIndex.drawer + 1,
          }}
        >
          <Toolbar sx={{ justifyContent: 'space-between', px: { xs: 2, md: 3 }, minHeight: '64px' }}>
            {/* Brand Logo & Breadcrumb Navigation */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Box
                sx={{
                  width: 36,
                  height: 36,
                  borderRadius: '10px',
                  background: 'linear-gradient(135deg, #6366f1 0%, #4338ca 100%)',
                  boxShadow: isDark ? '0 0 16px rgba(99, 102, 241, 0.4)' : '0 2px 8px rgba(99, 102, 241, 0.25)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#ffffff',
                }}
              >
                <AutoAwesomeIcon sx={{ fontSize: 20 }} />
              </Box>
              <Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700, fontSize: '0.95rem' }}>
                    Antigravity Quota
                  </Typography>
                  <Typography variant="body2" sx={{ color: isDark ? '#4b5563' : '#cbd5e1' }}>
                    /
                  </Typography>
                  <Typography
                    variant="caption"
                    sx={{
                      color: isDark ? '#9ca3af' : '#64748b',
                      fontWeight: 600,
                      fontFamily: 'monospace',
                      fontSize: '0.78rem',
                    }}
                  >
                    ge-ent-app-demo
                  </Typography>

                  {/* Pulsing Sync Dot */}
                  <Box
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 0.75,
                      ml: 1,
                      px: 1,
                      py: 0.25,
                      borderRadius: '12px',
                      backgroundColor: isDark ? 'rgba(16, 185, 129, 0.12)' : 'rgba(16, 185, 129, 0.1)',
                      border: `1px solid ${isDark ? 'rgba(16, 185, 129, 0.25)' : 'rgba(16, 185, 129, 0.2)'}`,
                    }}
                  >
                    <Box
                      sx={{
                        width: 6,
                        height: 6,
                        borderRadius: '50%',
                        backgroundColor: '#10b981',
                        boxShadow: '0 0 6px #10b981',
                      }}
                    />
                    <Typography
                      variant="caption"
                      sx={{
                        fontSize: '0.68rem',
                        fontWeight: 600,
                        color: isDark ? '#34d399' : '#059669',
                      }}
                    >
                      Sync Active
                    </Typography>
                  </Box>
                </Box>
                <Typography
                  variant="caption"
                  sx={{ color: isDark ? '#6b7280' : '#94a3b8', fontSize: '0.72rem', display: 'block' }}
                >
                  Enterprise AI Developer Quota & Directory Access Governance
                </Typography>
              </Box>
            </Box>

            {/* Action Bar */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Tooltip title="Refresh Dashboard Telemetry">
                <IconButton size="small" onClick={loadData} disabled={loading} sx={{ color: isDark ? '#9ca3af' : '#64748b' }}>
                  <RefreshIcon fontSize="small" />
                </IconButton>
              </Tooltip>

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

              {/* Theme Toggle Button */}
              <Tooltip title={`Switch to ${isDark ? 'Light' : 'Dark'} Mode`}>
                <IconButton size="small" onClick={toggleThemeMode} sx={{ color: isDark ? '#f59e0b' : '#6366f1' }}>
                  {isDark ? <LightModeOutlinedIcon fontSize="small" /> : <DarkModeOutlinedIcon fontSize="small" />}
                </IconButton>
              </Tooltip>

              {/* Quick Add Developer */}
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
                Add Dev
              </Button>

              {/* Publish & Sync Button */}
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
            </Box>
          </Toolbar>
        </AppBar>

        {/* Main Content Area */}
        <Container maxWidth="xl" sx={{ py: 3, flexGrow: 1 }}>
          <DisclaimerBanner />
          <KPISummary kpis={kpis} loading={loading} />
          <UserTable
            users={users}
            onSelectUser={handleSelectUser}
            onToggleLock={handleToggleLock}
            onToggleExempt={handleToggleExempt}
            onOpenAddUser={() => setAddUserOpen(true)}
          />
        </Container>

        {/* Drawer & Modals */}
        <UserDrawer
          user={selectedUser}
          config={config}
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
