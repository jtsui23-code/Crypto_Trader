// src/components/TraderDetailView.tsx
import { useEffect, useState } from 'react';
import { Box, Typography, List, Paper, Divider } from '@mui/material';

export const TraderDetailView = ({ trader }: { trader: any }) => {
  const [swaps, setSwaps] = useState([]);

  useEffect(() => {
    if (trader?.name) {
      // UPDATED: Fetch actual database history for this specific address
      fetch(`http://localhost:8000/api/swaps/${trader.name}`)
        .then(res => res.json())
        .then(data => setSwaps(data))
        .catch(err => console.error("History fetch error:", err));
    }
  }, [trader]);

  if (!trader) return (
    <Box sx={{ p: 4, textAlign: 'center' }}>
      <Typography color="gray">Select a wallet to view database history</Typography>
    </Box>
  );

  return (
    <Box sx={{ p: 4 }}>
      <Typography variant="h5" sx={{ color: 'cyan', mb: 1 }}>Wallet Activity</Typography>
      <Typography variant="body2" sx={{ color: '#9ca3af', mb: 4, fontFamily: 'monospace' }}>
        {trader.name}
      </Typography>
      <Divider sx={{ mb: 2, bgcolor: '#333' }} />
      <List>
        {swaps.length > 0 ? swaps.map((swap: any, i) => (
          <Paper key={i} sx={{ mb: 2, p: 2, bgcolor: '#1a1a1a', border: '1px solid #333', color: 'white' }}>
            <Typography variant="subtitle2" sx={{ color: '#4ade80' }}>
              Bought {swap.amount_in} (Mint: {swap.token_in.slice(0, 6)}...)
            </Typography>
            <Typography variant="body2" color="gray">
              Sold {swap.amount_out} (Mint: {swap.token_out.slice(0, 6)}...)
            </Typography>
            <Typography variant="caption" color="darkgray">
              {new Date(swap.time).toLocaleString()}
            </Typography>
          </Paper>
        )) : (
          <Typography color="gray">No swaps found in database for this wallet.</Typography>
        )}
      </List>
    </Box>
  );
};