import { createTheme, ThemeOptions } from '@mui/material/styles';

export const getTheme = (mode: 'dark' | 'light' = 'dark') => {
  const isDark = mode === 'dark';

  const themeOptions: ThemeOptions = {
    palette: {
      mode,
      primary: {
        main: '#6366f1', // Claude / Linear Indigo
        light: '#818cf8',
        dark: '#4f46e5',
        contrastText: '#ffffff',
      },
      secondary: {
        main: '#10b981', // Emerald Green
        light: '#34d399',
        dark: '#059669',
        contrastText: '#ffffff',
      },
      warning: {
        main: '#f59e0b', // Amber
        light: '#fbbf24',
        dark: '#d97706',
        contrastText: '#ffffff',
      },
      error: {
        main: '#ef4444', // Rose / Red
        light: '#f87171',
        dark: '#dc2626',
        contrastText: '#ffffff',
      },
      info: {
        main: '#3b82f6', // Electric Blue
        light: '#60a5fa',
        dark: '#2563eb',
        contrastText: '#ffffff',
      },
      background: {
        default: isDark ? '#090d16' : '#f8fafc',
        paper: isDark ? '#111827' : '#ffffff',
      },
      text: {
        primary: isDark ? '#f9fafb' : '#0f172a',
        secondary: isDark ? '#9ca3af' : '#64748b',
      },
      divider: isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0',
    },
    typography: {
      fontFamily: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      h5: {
        fontWeight: 600,
        letterSpacing: '-0.02em',
      },
      h6: {
        fontWeight: 600,
        letterSpacing: '-0.015em',
      },
      subtitle1: {
        fontWeight: 500,
        letterSpacing: '-0.01em',
      },
      subtitle2: {
        fontWeight: 500,
        color: isDark ? '#9ca3af' : '#64748b',
      },
      button: {
        textTransform: 'none',
        fontWeight: 500,
        letterSpacing: '0.01em',
      },
    },
    shape: {
      borderRadius: 10,
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: {
            backgroundColor: isDark ? '#090d16' : '#f8fafc',
            color: isDark ? '#f9fafb' : '#0f172a',
            scrollbarColor: isDark ? '#374151 transparent' : '#cbd5e1 transparent',
            '&::-webkit-scrollbar, & *::-webkit-scrollbar': {
              width: 8,
              height: 8,
            },
            '&::-webkit-scrollbar-thumb, & *::-webkit-scrollbar-thumb': {
              borderRadius: 8,
              backgroundColor: isDark ? '#374151' : '#cbd5e1',
            },
            '&::-webkit-scrollbar-track, & *::-webkit-scrollbar-track': {
              backgroundColor: 'transparent',
            },
          },
        },
      },
      MuiButton: {
        styleOverrides: {
          root: {
            borderRadius: 8,
            boxShadow: 'none',
            fontWeight: 500,
            transition: 'all 0.15s ease-in-out',
            '&:hover': {
              boxShadow: isDark ? '0 0 12px rgba(99, 102, 241, 0.25)' : '0 2px 8px rgba(0, 0, 0, 0.08)',
            },
          },
          containedPrimary: {
            backgroundColor: '#6366f1',
            '&:hover': {
              backgroundColor: '#4f46e5',
            },
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: {
            backgroundImage: 'none',
            borderRadius: 12,
            border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
          },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: {
            borderRadius: 12,
            border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
            backgroundImage: 'none',
            backgroundColor: isDark ? '#111827' : '#ffffff',
            transition: 'border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease',
            '&:hover': {
              borderColor: isDark ? 'rgba(99, 102, 241, 0.35)' : '#cbd5e1',
            },
          },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: {
            fontWeight: 500,
            borderRadius: 6,
          },
        },
      },
      MuiTableCell: {
        styleOverrides: {
          root: {
            borderBottom: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.06)' : '#f1f5f9'}`,
            padding: '14px 16px',
          },
          head: {
            fontWeight: 600,
            fontSize: '0.75rem',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            color: isDark ? '#9ca3af' : '#64748b',
            backgroundColor: isDark ? '#0f172a' : '#f8fafc',
          },
        },
      },
      MuiTableRow: {
        styleOverrides: {
          root: {
            transition: 'background-color 0.12s ease',
            '&:hover': {
              backgroundColor: isDark ? 'rgba(255, 255, 255, 0.02)' : 'rgba(0, 0, 0, 0.015)',
            },
          },
        },
      },
    },
  };

  return createTheme(themeOptions);
};

export const theme = getTheme('dark');
