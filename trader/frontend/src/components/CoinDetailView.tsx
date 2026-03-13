import { Box, Typography } from '@mui/material';

interface Coin {
  id: string;
  name: string;
  symbol: string;
  price: string;
}

interface CoinDetailViewProps {
  coin: Coin | null | undefined;
}

export const CoinDetailView = ({ coin }: CoinDetailViewProps) => {
  if (!coin) {
    return (
      <Box sx={{ flex: 1, p: 4, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Typography variant="h5" color="textSecondary">
          Select a coin to see details
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ flex: 1, p: 4 }}>
      <Typography variant="h4" gutterBottom>
        {coin.name} ({coin.symbol}) Overall Info
      </Typography>
      
      <Box sx={{ mt: 2, p: 3, bgcolor: 'rgba(255, 255, 255, 0.05)', borderRadius: 2 }}>
        <Typography variant="h6" color="primary">
          Current Price: {coin.price}
        </Typography>
        {/* You can add more detailed Solana-specific stats here later */}
      </Box>
    </Box>
  );
};