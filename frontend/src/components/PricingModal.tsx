import React, { useEffect, useState } from 'react';
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
  useTheme,
} from '@mui/material';
import PriceCheckIcon from '@mui/icons-material/PriceCheck';
import { ModelPricing } from '../types';

interface PricingModalProps {
  pricing: Record<string, ModelPricing>;
  open: boolean;
  onClose: () => void;
  onSave: (matrix: Record<string, ModelPricing>) => Promise<void>;
}

export const PricingModal: React.FC<PricingModalProps> = ({
  pricing,
  open,
  onClose,
  onSave,
}) => {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';

  const [matrix, setMatrix] = useState<Record<string, ModelPricing>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (pricing && Object.keys(pricing).length > 0) {
      setMatrix(JSON.parse(JSON.stringify(pricing)));
    }
  }, [pricing, open]);

  const handleChange = (
    modelKey: string,
    field: keyof ModelPricing,
    value: string
  ) => {
    const num = parseFloat(value) || 0;
    setMatrix((prev) => ({
      ...prev,
      [modelKey]: {
        ...prev[modelKey],
        [field]: num,
      },
    }));
  };

  const calculateBlended = (p: ModelPricing) => {
    const rate =
      p.estimated_input_ratio * p.input_price_per_million +
      p.estimated_output_ratio * p.output_price_per_million +
      p.estimated_cached_ratio * p.cached_price_per_million;
    return rate.toFixed(4);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(matrix);
      onClose();
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="lg"
      fullWidth
      PaperProps={{
        sx: {
          backgroundColor: isDark ? '#111827' : '#ffffff',
          backgroundImage: 'none',
          border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
          borderRadius: 3,
        },
      }}
    >
      <DialogTitle
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1.5,
          borderBottom: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
          pb: 2,
        }}
      >
        <Box
          sx={{
            width: 32,
            height: 32,
            borderRadius: '8px',
            backgroundColor: isDark ? 'rgba(99, 102, 241, 0.15)' : 'rgba(99, 102, 241, 0.1)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#6366f1',
          }}
        >
          <PriceCheckIcon fontSize="small" />
        </Box>
        <Box>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, color: isDark ? '#f9fafb' : '#0f172a' }}>
            Token Pricing & Hinge Point Matrix
          </Typography>
          <Typography variant="caption" sx={{ color: isDark ? '#9ca3af' : '#64748b' }}>
            Configure per-million token rates and prompt/completion/cache hinge ratios for Gemini models
          </Typography>
        </Box>
      </DialogTitle>

      <DialogContent sx={{ p: 2.5 }}>
        <TableContainer
          component={Paper}
          elevation={0}
          sx={{
            backgroundColor: isDark ? '#090d16' : '#f8fafc',
            border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
            borderRadius: 2,
          }}
        >
          <Table size="small">
            <TableHead
              sx={{
                backgroundColor: isDark ? 'rgba(255, 255, 255, 0.03)' : '#f1f5f9',
              }}
            >
              <TableRow>
                <TableCell sx={{ fontWeight: 600, color: isDark ? '#9ca3af' : '#64748b', fontSize: '0.78rem' }}>
                  Model / Variant
                </TableCell>
                <TableCell align="center" sx={{ fontWeight: 600, color: isDark ? '#9ca3af' : '#64748b', fontSize: '0.78rem' }}>
                  Input / 1M ($)
                </TableCell>
                <TableCell align="center" sx={{ fontWeight: 600, color: isDark ? '#9ca3af' : '#64748b', fontSize: '0.78rem' }}>
                  Output / 1M ($)
                </TableCell>
                <TableCell align="center" sx={{ fontWeight: 600, color: isDark ? '#9ca3af' : '#64748b', fontSize: '0.78rem' }}>
                  Cached / 1M ($)
                </TableCell>
                <TableCell align="center" sx={{ fontWeight: 600, color: isDark ? '#9ca3af' : '#64748b', fontSize: '0.78rem' }}>
                  Hinge Ratios (In / Out / Cache)
                </TableCell>
                <TableCell align="right" sx={{ fontWeight: 600, color: isDark ? '#9ca3af' : '#64748b', fontSize: '0.78rem' }}>
                  Blended / 1M
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {Object.entries(matrix).map(([key, model]) => (
                <TableRow
                  key={key}
                  sx={{
                    '&:hover': {
                      backgroundColor: isDark ? 'rgba(255, 255, 255, 0.02)' : 'rgba(0, 0, 0, 0.01)',
                    },
                  }}
                >
                  <TableCell>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Typography variant="body2" sx={{ fontWeight: 600, color: isDark ? '#f9fafb' : '#0f172a' }}>
                        {model.display_name}
                      </Typography>
                      {key.includes('3.8') && (
                        <Chip
                          label="Active"
                          size="small"
                          sx={{
                            height: 18,
                            fontSize: '0.65rem',
                            fontWeight: 600,
                            backgroundColor: isDark ? 'rgba(99, 102, 241, 0.2)' : 'rgba(99, 102, 241, 0.1)',
                            color: '#818cf8',
                          }}
                        />
                      )}
                    </Box>
                    <Typography
                      variant="caption"
                      sx={{
                        color: isDark ? '#6b7280' : '#94a3b8',
                        fontFamily: 'monospace',
                        fontSize: '0.72rem',
                        display: 'block',
                        mt: 0.25,
                      }}
                    >
                      Pattern: {model.log_pattern}
                    </Typography>
                  </TableCell>

                  <TableCell align="center">
                    <TextField
                      size="small"
                      type="number"
                      value={model.input_price_per_million}
                      onChange={(e) => handleChange(key, 'input_price_per_million', e.target.value)}
                      sx={{ width: 90 }}
                      inputProps={{
                        step: 0.01,
                        min: 0,
                        style: { fontFamily: 'monospace', fontSize: '0.82rem', textAlign: 'center' },
                      }}
                    />
                  </TableCell>

                  <TableCell align="center">
                    <TextField
                      size="small"
                      type="number"
                      value={model.output_price_per_million}
                      onChange={(e) => handleChange(key, 'output_price_per_million', e.target.value)}
                      sx={{ width: 90 }}
                      inputProps={{
                        step: 0.01,
                        min: 0,
                        style: { fontFamily: 'monospace', fontSize: '0.82rem', textAlign: 'center' },
                      }}
                    />
                  </TableCell>

                  <TableCell align="center">
                    <TextField
                      size="small"
                      type="number"
                      value={model.cached_price_per_million}
                      onChange={(e) => handleChange(key, 'cached_price_per_million', e.target.value)}
                      sx={{ width: 90 }}
                      inputProps={{
                        step: 0.005,
                        min: 0,
                        style: { fontFamily: 'monospace', fontSize: '0.82rem', textAlign: 'center' },
                      }}
                    />
                  </TableCell>

                  <TableCell align="center">
                    <Typography
                      variant="caption"
                      sx={{
                        fontWeight: 600,
                        fontFamily: 'monospace',
                        color: isDark ? '#cbd5e1' : '#475569',
                        fontSize: '0.78rem',
                      }}
                    >
                      {(model.estimated_input_ratio * 100).toFixed(0)}% / {(model.estimated_output_ratio * 100).toFixed(0)}% / {(model.estimated_cached_ratio * 100).toFixed(0)}%
                    </Typography>
                  </TableCell>

                  <TableCell align="right">
                    <Typography
                      variant="body2"
                      sx={{
                        fontWeight: 700,
                        fontFamily: 'monospace',
                        color: '#6366f1',
                      }}
                    >
                      ${calculateBlended(model)}
                    </Typography>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </DialogContent>

      <DialogActions
        sx={{
          px: 3,
          py: 2,
          borderTop: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'}`,
        }}
      >
        <Button variant="outlined" onClick={onClose} disabled={saving} sx={{ borderRadius: 2 }}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handleSave}
          disabled={saving}
          sx={{
            borderRadius: 2,
            backgroundColor: '#6366f1',
            '&:hover': { backgroundColor: '#4f46e5' },
          }}
        >
          {saving ? 'Saving...' : 'Save Pricing Matrix'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
