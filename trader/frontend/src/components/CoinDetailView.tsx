import { Box, Typography, Divider, Paper } from '@mui/material';

interface Coin {
  id: string;
  symbol: string;
  amount: number;
  entry_price: number;
  peak_price: number;
  cost_basis: number;
  wallet_address: string;
}

export const CoinDetailView = ({ coin }: { coin: Coin | null | undefined }) => {
  if (!coin) {
    return (
      <Box sx={{ flex: 1, p: 4, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Typography variant="h5">Select a position</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ flex: 1, p: 4 }}>
      <Typography variant="h4" sx={{ color: '#4ade80', mb: 1 }}>{coin.symbol}</Typography>
      <Typography variant="caption" sx={{ display: 'block', mb: 3, fontFamily: 'monospace' }}>
        Mint: {coin.id}
      </Typography>

      <Divider sx={{ mb: 4 }} />

      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2, mb: 3 }}>
        <Paper variant="outlined" sx={{ p: 2, border: 1, borderColor: 'divider' }}>
          <Typography variant="overline">Holdings</Typography>
          <Typography variant="h6">{coin.amount.toLocaleString()}</Typography>
        </Paper>
        <Paper variant="outlined" sx={{ p: 2, border: 1, borderColor: 'divider' }}>
          <Typography variant="overline">Cost Basis</Typography>
          <Typography variant="h6">${coin.cost_basis.toFixed(2)}</Typography>
        </Paper>
      </Box>

      <Paper variant="outlined" sx={{ p: 2, mb: 2, border: 1, borderColor: 'divider'}}>
        <Typography variant="overline">Entry Price</Typography>
        <Typography variant="h6">${coin.entry_price.toFixed(8)}</Typography>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2, border: 1, borderColor: 'divider' }}>
        <Typography variant="overline">Source Whale</Typography>
        <Typography variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
          {coin.wallet_address}
        </Typography>
      </Paper>
    </Box>
  );
};