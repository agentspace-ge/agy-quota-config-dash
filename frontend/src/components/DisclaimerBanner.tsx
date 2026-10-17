import React from 'react';
import { Paper, Typography, useTheme } from '@mui/material';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';

export const DisclaimerBanner: React.FC = () => {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';

  return (
    <Paper
      elevation={0}
      sx={{
        px: 2,
        py: 1.25,
        mb: 3,
        display: 'flex',
        alignItems: 'center',
        gap: 1.5,
        backgroundColor: isDark ? 'rgba(99, 102, 241, 0.08)' : 'rgba(99, 102, 241, 0.06)',
        border: `1px solid ${isDark ? 'rgba(99, 102, 241, 0.2)' : 'rgba(99, 102, 241, 0.25)'}`,
        borderRadius: 2,
      }}
    >
      <InfoOutlinedIcon sx={{ color: isDark ? '#818cf8' : '#4f46e5', fontSize: 18, flexShrink: 0 }} />
      <Typography
        variant="caption"
        sx={{
          color: isDark ? '#c7d2fe' : '#3730a3',
          fontWeight: 500,
          lineHeight: 1.45,
          fontSize: '0.8rem',
        }}
      >
        <strong style={{ fontWeight: 600 }}>Estimation Notice:</strong> Token breakdown percentages, gross spend figures, credit balances, and net cost metrics are estimated projections calculated from raw token telemetry logs and configured model pricing assumptions.
      </Typography>
    </Paper>
  );
};
