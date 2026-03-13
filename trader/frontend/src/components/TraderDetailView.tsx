// src/components/TraderDetailView.tsx
import { Box, Typography } from '@mui/material';

interface TraderDetailViewProps {
  trader: { name: string; record: string } | null | undefined;
}

export const TraderDetailView = ({ trader }: TraderDetailViewProps) => {
  if (!trader) {
    return (
      <Box sx={{ flex: 1, p: 4, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Typography variant="h5" color="textSecondary">Select a trader to view stats</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ flex: 1, p: 4 }}>
      <Typography variant="h4" gutterBottom>{trader.name}'s Performance</Typography>
      <Box sx={{ mt: 2, p: 3, bgcolor: 'rgba(0, 255, 255, 0.05)', border: '1px solid cyan', borderRadius: 2 }}>
        <Typography variant="h6">Record: {trader.record}</Typography>
        <Typography variant="body1" sx={{ mt: 1 }}>Recent Activity: Buying $SOL</Typography>
      </Box>
    </Box>
  );
};