import { useEffect, useState, useRef } from 'react';
import { Box, Typography, List, Paper, Divider, Grid, Fade } from '@mui/material';
import { PieChart } from '@mui/x-charts/PieChart';
import { BarChart } from '@mui/x-charts/BarChart';

export const TraderDetailView = ({ trader }: { trader: any }) => {
  const [swaps, setSwaps] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  
  const lastTraderRef = useRef<string | null>(null);

  useEffect(() => {
    if (trader?.name) {
      const isNewTrader = lastTraderRef.current !== trader.name;
      
      if (isNewTrader) {
        setLoading(true);
        setSwaps([]);
        lastTraderRef.current = trader.name;
      }

      fetch(`http://localhost:8000/api/swaps/${trader.name}`)
        .then(res => res.json())
        .then(data => {
          setSwaps(data);
          setLoading(false);
        })
        .catch(err => {
          console.error("History fetch error:", err);
          setLoading(false);
        });
    }
  }, [trader]);

  if (!trader) return (
    <Box sx={{ p: 4, textAlign: 'center' }}>
      <Typography color="gray">Select a wallet to view performance analytics</Typography>
    </Box>
  );

  return (
    <Fade in={true} key={trader.name} timeout={400}>
      <Box sx={{ p: 4 }}>
        <Typography variant="h5" sx={{ color: "var(--accent-color)", mb: 1 }}>Trader Performance</Typography>
        <Typography variant="body2" sx={{ mb: 4, fontFamily: 'monospace' }}>
          {trader.name}
        </Typography>

        <Grid container spacing={3} sx={{ mb: 4 }}>
          <Grid item xs={12}>
            <Paper variant="outlined" sx={{ p: 2, border: 1, borderColor: 'divider', bgcolor: 'background.paper' }}>
              <Typography variant="overline">Win/Loss Distribution</Typography>
              <PieChart
                series={[{
                  data: [
                    { id: 0, value: trader.winning_trades || 0, label: 'Wins', color: 'success.main' },
                    { id: 1, value: trader.losing_trades || 0, label: 'Losses', color: 'error.main' },
                  ],
                  innerRadius: 30,
                  paddingAngle: 5,
                  cornerRadius: 5,
                }]}
                height={200}
                width={250}
                slotProps={{ legend: { labelStyle: { fill: 'white' } } }}
              />
            </Paper>
          </Grid>

          <Grid item xs={12}>
            <Paper variant="outlined" sx={{ p: 2, border: 1, borderColor: 'divider', bgcolor: 'background.paper' }}>
              <Typography variant="overline">PnL Metrics</Typography>
              <BarChart
                xAxis={[{ scaleType: 'band', data: ['Best', 'Worst', 'Avg'] }]}
                series={[{ 
                  data: [
                    trader.best_trade_pnl || 0, 
                    trader.worst_trade_pnl || 0, 
                    trader.avg_pnl_per_trade || 0
                  ],
                  color: 'var(--accent-color)' 
                }]}
                height={200}
                width={300}
              />
            </Paper>
          </Grid>
        </Grid>

        <Divider sx={{ mb: 2 }} />
        
        <Typography variant="h6" sx={{ mb: 2 }}>Recent Swaps</Typography>
        
        <List>
          {loading ? null : swaps.length > 0 ? (
            swaps.map((swap: any, i) => (
              <Fade in={true} key={`${trader.name}-${i}`}>
                <Paper variant="outlined" sx={{ mb: 2, p: 2, border: 1, borderColor: 'divider', bgcolor: 'background.paper' }}>
                  <Typography variant="subtitle2" sx={{ color: 'success.main' }}>
                    Bought {swap.amount_in} ({swap.token_in.slice(0, 6)}...)
                  </Typography>
                  <Typography variant="body2">
                    Sold {swap.amount_out} ({swap.token_out.slice(0, 6)}...)
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {new Date(swap.time).toLocaleString()}
                  </Typography>
                </Paper>
              </Fade>
            ))
          ) : (
            <Typography color="text.secondary">No swaps found for this wallet.</Typography>
          )}
        </List>
      </Box>
    </Fade>
  );
};