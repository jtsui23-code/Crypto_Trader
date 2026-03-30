import { Box, Typography, Divider } from '@mui/material';

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
        <Typography variant="h5" color="textSecondary">Select a position</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ flex: 1, p: 4 }}>
      <Typography variant="h4" sx={{ color: '#4ade80', mb: 1 }}>{coin.symbol}</Typography>
      <Typography variant="caption" sx={{ color: 'gray', display: 'block', mb: 3, fontFamily: 'monospace' }}>
        Mint: {coin.id}
      </Typography>

      <Divider sx={{ mb: 4, bgcolor: '#333' }} />

      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2, mb: 3 }}>
        <Box sx={{ p: 2, bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 2, border: '1px solid #333' }}>
          <Typography variant="overline" color="gray">Holdings</Typography>
          <Typography variant="h6">{coin.amount.toLocaleString()}</Typography>
        </Box>
        <Box sx={{ p: 2, bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 2, border: '1px solid #333' }}>
          <Typography variant="overline" color="gray">Cost Basis</Typography>
          <Typography variant="h6">${coin.cost_basis.toFixed(2)}</Typography>
        </Box>
      </Box>

      <Box sx={{ p: 2, mb: 2, bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 2, border: '1px solid #333' }}>
        <Typography variant="overline" color="gray">Entry Price</Typography>
        <Typography variant="h6">${coin.entry_price.toFixed(8)}</Typography>
      </Box>

      <Box sx={{ p: 2, bgcolor: 'rgba(32, 141, 209, 0.1)', borderRadius: 2, border: '1px solid #208dd1' }}>
        <Typography variant="overline" sx={{ color: '#208dd1' }}>Source Whale</Typography>
        <Typography variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
          {coin.wallet_address}
        </Typography>
      </Box>
    </Box>
  );
};