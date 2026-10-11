import React, { useState } from 'react';
import {
  Avatar,
  Box,
  Button,
  Chip,
  IconButton,
  InputAdornment,
  LinearProgress,
  Menu,
  MenuItem,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  TextField,
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import LockOpenIcon from '@mui/icons-material/LockOpen';
import LockIcon from '@mui/icons-material/Lock';
import VerifiedUserOutlinedIcon from '@mui/icons-material/VerifiedUserOutlined';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import PersonAddOutlinedIcon from '@mui/icons-material/PersonAddOutlined';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import CheckIcon from '@mui/icons-material/Check';
import { User } from '../types';

interface UserTableProps {
  users: User[];
  nextResetUtc?: string | null;
  onSelectUser: (user: User) => void;
  onToggleLock: (email: string) => void;
  onToggleExempt: (user: User) => void;
  onOpenAddUser: () => void;
}

export const UserTable: React.FC<UserTableProps> = ({
  users,
  nextResetUtc,
  onSelectUser,
  onToggleLock,
  onToggleExempt,
  onOpenAddUser,
}) => {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';

  const [search, setSearch] = useState('');
  const [filterStatus, setFilterStatus] = useState<string>('ALL');
  const [sortField, setSortField] = useState<'gross_spend' | 'tokens' | 'email' | 'utilization' | 'remaining_credit'>('gross_spend');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [copiedEmail, setCopiedEmail] = useState<string | null>(null);

  // Menu action state
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const [activeMenuUser, setActiveMenuUser] = useState<User | null>(null);

  const handleOpenMenu = (event: React.MouseEvent<HTMLElement>, user: User) => {
    event.stopPropagation();
    setMenuAnchor(event.currentTarget);
    setActiveMenuUser(user);
  };

  const handleCloseMenu = () => {
    setMenuAnchor(null);
    setActiveMenuUser(null);
  };

  const handleCopyEmail = (e: React.MouseEvent, email: string) => {
    e.stopPropagation();
    navigator.clipboard.writeText(email);
    setCopiedEmail(email);
    setTimeout(() => setCopiedEmail(null), 2000);
  };

  const handleSort = (field: 'gross_spend' | 'tokens' | 'email' | 'utilization' | 'remaining_credit') => {
    if (sortField === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortOrder('desc');
    }
  };

  const formatRelativeTime = (isoString?: string | null) => {
    if (!isoString) return 'Inactive';
    const now = new Date();
    const date = new Date(isoString);
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  const getStatusChip = (user: User) => {
    if (user.is_exempt) {
      return (
        <Chip
          label="Exempt"
          size="small"
          sx={{
            backgroundColor: isDark ? 'rgba(99, 102, 241, 0.15)' : 'rgba(99, 102, 241, 0.1)',
            color: isDark ? '#a5b4fc' : '#4f46e5',
            border: `1px solid ${isDark ? 'rgba(99, 102, 241, 0.3)' : 'rgba(99, 102, 241, 0.25)'}`,
            fontWeight: 600,
            fontSize: '0.72rem',
            height: 22,
          }}
        />
      );
    }
    if (user.status === 'MANUALLY_DISABLED') {
      return (
        <Chip
          label="Locked"
          size="small"
          icon={<LockIcon sx={{ fontSize: '13px !important', color: 'inherit !important' }} />}
          sx={{
            backgroundColor: isDark ? 'rgba(156, 163, 175, 0.12)' : 'rgba(100, 116, 139, 0.1)',
            color: isDark ? '#9ca3af' : '#475569',
            border: `1px solid ${isDark ? 'rgba(156, 163, 175, 0.25)' : 'rgba(100, 116, 139, 0.25)'}`,
            fontWeight: 600,
            fontSize: '0.72rem',
            height: 22,
          }}
        />
      );
    }
    if (user.status === 'AUTO_DISABLED') {
      const tooltipMsg = nextResetUtc
        ? `Over weekly quota limit. Automatically re-enables at weekly pool reset: ${new Date(nextResetUtc).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`
        : 'Over weekly quota limit. Automatically re-enables on next credit pool reset.';
      return (
        <Tooltip title={tooltipMsg} arrow>
          <Chip
            label="Auto-Throttled"
            size="small"
            sx={{
              backgroundColor: isDark ? 'rgba(239, 68, 68, 0.15)' : 'rgba(239, 68, 68, 0.1)',
              color: isDark ? '#f87171' : '#dc2626',
              border: `1px solid ${isDark ? 'rgba(239, 68, 68, 0.3)' : 'rgba(239, 68, 68, 0.25)'}`,
              fontWeight: 600,
              fontSize: '0.72rem',
              height: 22,
            }}
          />
        </Tooltip>
      );
    }
    if (user.current_week.credit_utilization_percentage >= 80) {
      return (
        <Chip
          label="Warning (>80%)"
          size="small"
          sx={{
            backgroundColor: isDark ? 'rgba(245, 158, 11, 0.15)' : 'rgba(245, 158, 11, 0.1)',
            color: isDark ? '#fbbf24' : '#d97706',
            border: `1px solid ${isDark ? 'rgba(245, 158, 11, 0.3)' : 'rgba(245, 158, 11, 0.25)'}`,
            fontWeight: 600,
            fontSize: '0.72rem',
            height: 22,
          }}
        />
      );
    }
    return (
      <Chip
        label="Active"
        size="small"
        sx={{
          backgroundColor: isDark ? 'rgba(16, 185, 129, 0.15)' : 'rgba(16, 185, 129, 0.1)',
          color: isDark ? '#34d399' : '#059669',
          border: `1px solid ${isDark ? 'rgba(16, 185, 129, 0.3)' : 'rgba(16, 185, 129, 0.25)'}`,
          fontWeight: 600,
          fontSize: '0.72rem',
          height: 22,
        }}
      />
    );
  };

  // Status counts for filter chips
  const counts = {
    ALL: users.length,
    ACTIVE: users.filter((u) => u.status === 'ACTIVE' && !u.is_exempt && u.current_week.credit_utilization_percentage < 80).length,
    WARNING: users.filter((u) => u.status === 'ACTIVE' && !u.is_exempt && u.current_week.credit_utilization_percentage >= 80).length,
    THROTTLED: users.filter((u) => u.status === 'AUTO_DISABLED').length,
    LOCKED: users.filter((u) => u.status === 'MANUALLY_DISABLED').length,
    EXEMPT: users.filter((u) => u.is_exempt).length,
  };

  // Filter users
  const filteredUsers = users.filter((u) => {
    const matchesSearch = u.email.toLowerCase().includes(search.toLowerCase());
    if (!matchesSearch) return false;

    if (filterStatus === 'ALL') return true;
    if (filterStatus === 'EXEMPT') return u.is_exempt;
    if (filterStatus === 'LOCKED') return u.status === 'MANUALLY_DISABLED';
    if (filterStatus === 'THROTTLED') return u.status === 'AUTO_DISABLED';
    if (filterStatus === 'WARNING') return u.status === 'ACTIVE' && !u.is_exempt && u.current_week.credit_utilization_percentage >= 80;
    if (filterStatus === 'ACTIVE') return u.status === 'ACTIVE' && !u.is_exempt && u.current_week.credit_utilization_percentage < 80;
    return true;
  });

  // Sort users
  filteredUsers.sort((a, b) => {
    let comp = 0;
    if (sortField === 'gross_spend') {
      comp = a.current_week.gross_spend_usd - b.current_week.gross_spend_usd;
    } else if (sortField === 'tokens') {
      comp = a.current_week.total_tokens - b.current_week.total_tokens;
    } else if (sortField === 'email') {
      comp = a.email.localeCompare(b.email);
    } else if (sortField === 'utilization') {
      comp = a.current_week.credit_utilization_percentage - b.current_week.credit_utilization_percentage;
    } else if (sortField === 'remaining_credit') {
      comp = a.current_week.remaining_credit_usd - b.current_week.remaining_credit_usd;
    }
    return sortOrder === 'desc' ? -comp : comp;
  });

  return (
    <Paper
      elevation={0}
      sx={{
        border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
        borderRadius: 3,
        overflow: 'hidden',
        backgroundColor: isDark ? '#111827' : '#ffffff',
      }}
    >
      {/* Search & Filter Header Bar */}
      <Box
        sx={{
          p: 2,
          display: 'flex',
          flexWrap: 'wrap',
          gap: 2,
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.06)' : '#f1f5f9'}`,
          backgroundColor: isDark ? '#0b0f19' : '#fafafa',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: '1 1 280px', maxWidth: 420 }}>
          <TextField
            size="small"
            fullWidth
            placeholder="Search developers by email... (Press / to focus)"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon sx={{ color: isDark ? '#6b7280' : '#94a3b8', fontSize: 19 }} />
                </InputAdornment>
              ),
              sx: {
                borderRadius: 2,
                fontSize: '0.85rem',
                backgroundColor: isDark ? '#111827' : '#ffffff',
              },
            }}
          />
        </Box>

        {/* Filter Pills with Live Counts */}
        <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', alignItems: 'center' }}>
          {[
            { id: 'ALL', label: 'All', count: counts.ALL },
            { id: 'ACTIVE', label: 'Active', count: counts.ACTIVE },
            { id: 'WARNING', label: 'Warning', count: counts.WARNING },
            { id: 'THROTTLED', label: 'Throttled', count: counts.THROTTLED },
            { id: 'LOCKED', label: 'Locked', count: counts.LOCKED },
            { id: 'EXEMPT', label: 'Exempt', count: counts.EXEMPT },
          ].map((item) => {
            const isSelected = filterStatus === item.id;
            return (
              <Chip
                key={item.id}
                label={`${item.label} (${item.count})`}
                clickable
                onClick={() => setFilterStatus(item.id)}
                size="small"
                sx={{
                  fontWeight: isSelected ? 600 : 500,
                  fontSize: '0.75rem',
                  backgroundColor: isSelected
                    ? isDark
                      ? '#6366f1'
                      : '#4f46e5'
                    : isDark
                    ? 'rgba(255, 255, 255, 0.05)'
                    : '#f1f5f9',
                  color: isSelected ? '#ffffff' : isDark ? '#9ca3af' : '#475569',
                  border: `1px solid ${
                    isSelected
                      ? 'transparent'
                      : isDark
                      ? 'rgba(255, 255, 255, 0.06)'
                      : '#e2e8f0'
                  }`,
                  '&:hover': {
                    backgroundColor: isSelected
                      ? '#4f46e5'
                      : isDark
                      ? 'rgba(255, 255, 255, 0.1)'
                      : '#e2e8f0',
                  },
                }}
              />
            );
          })}

          <Button
            variant="contained"
            size="small"
            startIcon={<PersonAddOutlinedIcon sx={{ fontSize: 17 }} />}
            onClick={onOpenAddUser}
            sx={{
              ml: 1,
              borderRadius: 2,
              px: 1.75,
              fontSize: '0.8rem',
              backgroundColor: '#6366f1',
              '&:hover': { backgroundColor: '#4f46e5' },
            }}
          >
            Add Developer
          </Button>
        </Box>
      </Box>

      {/* Main Table */}
      <TableContainer>
        <Table sx={{ minWidth: 800 }}>
          <TableHead>
            <TableRow>
              <TableCell>
                <TableSortLabel
                  active={sortField === 'email'}
                  direction={sortField === 'email' ? sortOrder : 'asc'}
                  onClick={() => handleSort('email')}
                >
                  Developer
                </TableSortLabel>
              </TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">
                <TableSortLabel
                  active={sortField === 'tokens'}
                  direction={sortField === 'tokens' ? sortOrder : 'desc'}
                  onClick={() => handleSort('tokens')}
                >
                  Weekly Tokens
                </TableSortLabel>
              </TableCell>
              <TableCell align="right">
                <TableSortLabel
                  active={sortField === 'gross_spend'}
                  direction={sortField === 'gross_spend' ? sortOrder : 'desc'}
                  onClick={() => handleSort('gross_spend')}
                >
                  Gross Usage
                </TableSortLabel>
              </TableCell>
              <TableCell align="right">Quota Credits</TableCell>
              <TableCell align="right">
                <TableSortLabel
                  active={sortField === 'remaining_credit'}
                  direction={sortField === 'remaining_credit' ? sortOrder : 'desc'}
                  onClick={() => handleSort('remaining_credit')}
                >
                  Balance / Overages
                </TableSortLabel>
              </TableCell>
              <TableCell sx={{ minWidth: 170 }}>
                <TableSortLabel
                  active={sortField === 'utilization'}
                  direction={sortField === 'utilization' ? sortOrder : 'desc'}
                  onClick={() => handleSort('utilization')}
                >
                  Utilization
                </TableSortLabel>
              </TableCell>
              <TableCell>Last Active</TableCell>
              <TableCell align="center">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filteredUsers.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} align="center" sx={{ py: 6 }}>
                  <Typography variant="body2" sx={{ color: isDark ? '#9ca3af' : '#64748b' }}>
                    No developers match the specified search or filter criteria.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              filteredUsers.map((user) => {
                const current = user.current_week;
                const utilization = current.credit_utilization_percentage;
                const isOver = current.net_billable_cost_usd > 0;

                // Color token according to quota health
                const progressColor =
                  utilization > 100
                    ? '#ef4444'
                    : utilization >= 80
                    ? '#f59e0b'
                    : '#10b981';

                return (
                  <TableRow
                    key={user.email}
                    hover
                    onClick={() => onSelectUser(user)}
                    sx={{
                      cursor: 'pointer',
                      transition: 'background-color 0.12s ease',
                      '&:hover': {
                        backgroundColor: isDark
                          ? 'rgba(99, 102, 241, 0.04) !important'
                          : 'rgba(99, 102, 241, 0.03) !important',
                      },
                    }}
                  >
                    {/* Developer Identity */}
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                        <Avatar
                          sx={{
                            width: 32,
                            height: 32,
                            fontSize: '0.85rem',
                            fontWeight: 600,
                            backgroundColor: isDark ? '#1f2937' : '#e2e8f0',
                            color: isDark ? '#c7d2fe' : '#3730a3',
                            border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.1)' : '#cbd5e1'}`,
                          }}
                        >
                          {user.email.charAt(0).toUpperCase()}
                        </Avatar>
                        <Box sx={{ minWidth: 0 }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                            <Typography
                              variant="body2"
                              sx={{
                                fontWeight: 600,
                                color: isDark ? '#f3f4f6' : '#1e293b',
                                fontSize: '0.875rem',
                              }}
                            >
                              {user.email}
                            </Typography>
                            <Tooltip title={copiedEmail === user.email ? 'Copied!' : 'Copy email'}>
                              <IconButton
                                size="small"
                                onClick={(e) => handleCopyEmail(e, user.email)}
                                sx={{ p: 0.25, color: isDark ? '#6b7280' : '#94a3b8' }}
                              >
                                {copiedEmail === user.email ? (
                                  <CheckIcon sx={{ fontSize: 13, color: '#10b981' }} />
                                ) : (
                                  <ContentCopyIcon sx={{ fontSize: 13 }} />
                                )}
                              </IconButton>
                            </Tooltip>
                          </Box>
                          <Typography
                            variant="caption"
                            sx={{ color: isDark ? '#6b7280' : '#94a3b8', fontSize: '0.72rem' }}
                          >
                            {user.has_custom_quota ? 'Custom Quota' : 'Org Default Quota'}
                          </Typography>
                        </Box>
                      </Box>
                    </TableCell>

                    {/* Status Chip */}
                    <TableCell>{getStatusChip(user)}</TableCell>

                    {/* Weekly Tokens */}
                    <TableCell align="right">
                      <Typography
                        variant="body2"
                        sx={{
                          fontFamily: 'monospace',
                          fontWeight: 600,
                          color: isDark ? '#f9fafb' : '#0f172a',
                          fontSize: '0.85rem',
                        }}
                      >
                        {current.total_tokens.toLocaleString()}
                      </Typography>
                    </TableCell>

                    {/* Gross Spend */}
                    <TableCell align="right">
                      <Typography
                        variant="body2"
                        sx={{
                          fontFamily: 'monospace',
                          fontWeight: 600,
                          color: isDark ? '#f9fafb' : '#0f172a',
                          fontSize: '0.85rem',
                        }}
                      >
                        ${current.gross_spend_usd.toFixed(2)}
                      </Typography>
                    </TableCell>

                    {/* Quota Credits */}
                    <TableCell align="right">
                      <Typography
                        variant="body2"
                        sx={{
                          fontFamily: 'monospace',
                          color: isDark ? '#9ca3af' : '#64748b',
                          fontSize: '0.85rem',
                        }}
                      >
                        ${current.quota_credits_usd.toFixed(2)}
                      </Typography>
                    </TableCell>

                    {/* Balance / Overages */}
                    <TableCell align="right">
                      {isOver ? (
                        <Box sx={{ display: 'inline-flex', alignItems: 'baseline', gap: 0.5 }}>
                          <Typography
                            variant="body2"
                            sx={{
                              fontFamily: 'monospace',
                              fontWeight: 700,
                              color: '#ef4444',
                              fontSize: '0.85rem',
                            }}
                          >
                            +${current.net_billable_cost_usd.toFixed(2)}
                          </Typography>
                          <Typography
                            variant="caption"
                            sx={{
                              fontSize: '0.72rem',
                              fontWeight: 600,
                              color: '#ef4444',
                            }}
                          >
                            over
                          </Typography>
                        </Box>
                      ) : (
                        <Box sx={{ display: 'inline-flex', alignItems: 'baseline', gap: 0.5 }}>
                          <Typography
                            variant="body2"
                            sx={{
                              fontFamily: 'monospace',
                              fontWeight: 600,
                              color: '#10b981',
                              fontSize: '0.85rem',
                            }}
                          >
                            ${current.remaining_credit_usd.toFixed(2)}
                          </Typography>
                          <Typography
                            variant="caption"
                            sx={{
                              fontSize: '0.72rem',
                              fontWeight: 500,
                              color: isDark ? '#9ca3af' : '#64748b',
                            }}
                          >
                            left
                          </Typography>
                        </Box>
                      )}
                    </TableCell>

                    {/* Utilization Progress Bar */}
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Box sx={{ flexGrow: 1 }}>
                          <LinearProgress
                            variant="determinate"
                            value={Math.min(100, utilization)}
                            sx={{
                              height: 6,
                              borderRadius: 3,
                              backgroundColor: isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0',
                              '& .MuiLinearProgress-bar': {
                                borderRadius: 3,
                                backgroundColor: progressColor,
                              },
                            }}
                          />
                        </Box>
                        <Typography
                          variant="caption"
                          sx={{
                            fontFamily: 'monospace',
                            fontWeight: 600,
                            minWidth: 42,
                            textAlign: 'right',
                            color: progressColor,
                            fontSize: '0.78rem',
                          }}
                        >
                          {utilization.toFixed(0)}%
                        </Typography>
                      </Box>
                    </TableCell>

                    {/* Last Active */}
                    <TableCell>
                      <Typography
                        variant="caption"
                        sx={{
                          color: isDark ? '#9ca3af' : '#64748b',
                          fontSize: '0.78rem',
                        }}
                      >
                        {formatRelativeTime(current.last_active)}
                      </Typography>
                    </TableCell>

                    {/* Actions Menu */}
                    <TableCell align="center" onClick={(e) => e.stopPropagation()}>
                      <IconButton
                        size="small"
                        onClick={(e) => handleOpenMenu(e, user)}
                        sx={{ color: isDark ? '#9ca3af' : '#64748b' }}
                      >
                        <MoreVertIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Row Context Menu */}
      <Menu
        anchorEl={menuAnchor}
        open={Boolean(menuAnchor)}
        onClose={handleCloseMenu}
        PaperProps={{
          elevation: 3,
          sx: {
            borderRadius: 2,
            minWidth: 180,
            border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
            backgroundColor: isDark ? '#1f2937' : '#ffffff',
          },
        }}
      >
        <MenuItem
          onClick={() => {
            if (activeMenuUser) onSelectUser(activeMenuUser);
            handleCloseMenu();
          }}
          sx={{ gap: 1.5, fontSize: '0.85rem' }}
        >
          <EditOutlinedIcon fontSize="small" sx={{ color: '#6366f1' }} />
          Edit Quota & Details
        </MenuItem>
        <MenuItem
          onClick={() => {
            if (activeMenuUser) onToggleLock(activeMenuUser.email);
            handleCloseMenu();
          }}
          sx={{ gap: 1.5, fontSize: '0.85rem' }}
        >
          {activeMenuUser?.status === 'MANUALLY_DISABLED' ? (
            <>
              <LockOpenIcon fontSize="small" sx={{ color: '#10b981' }} />
              Unlock Developer
            </>
          ) : (
            <>
              <LockIcon fontSize="small" sx={{ color: '#ef4444' }} />
              Manually Lock Developer
            </>
          )}
        </MenuItem>
        <MenuItem
          onClick={() => {
            if (activeMenuUser) onToggleExempt(activeMenuUser);
            handleCloseMenu();
          }}
          sx={{ gap: 1.5, fontSize: '0.85rem' }}
        >
          <VerifiedUserOutlinedIcon fontSize="small" sx={{ color: '#f59e0b' }} />
          {activeMenuUser?.is_exempt ? 'Remove Exemption' : 'Mark as Exempt'}
        </MenuItem>
      </Menu>
    </Paper>
  );
};
