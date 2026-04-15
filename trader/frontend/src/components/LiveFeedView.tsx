import { useState, useEffect } from 'react';
import { Box, Typography, Paper, List, ListItem, Chip } from '@mui/material';

interface TradeEvent {
  symbol: string;
  side: string;
  price: number;
  amount: number;
  usd_value: number;
  sell_reason: string | null;
  realised_pnl: number | null;
  timestamp: string;
  wallet_address: string;
}

const updateIntervalMs = 3000;

export function LiveFeedView() {
  const [feed, setFeed] = useState<TradeEvent[]>([]);
  const [accountBalance, setAccountBalance] = useState<number | null>(null);
  const [investedValue, setInvestedValue] = useState<number>(0);

  useEffect(() => {
    // Fetch initial state on mount
    const fetchInitialState = () => {
      fetch('http://localhost:8000/api/live-feed')
        .then(res => res.json())
        .then(data => setFeed(Array.isArray(data) ? data : []));

      fetch('http://localhost:8000/api/analytics/summary')
        .then(res => res.json())
        .then(data => { if (data?.account) setAccountBalance(data.account.balance); });

      fetch('http://localhost:8000/api/portfolio/positions')
        .then(res => res.json())
        .then(data => {
          const positions = Array.isArray(data) ? data : [];
          setInvestedValue(positions.reduce((sum, pos) => sum + (pos.cost_basis || 0), 0));
        });
    };

    fetchInitialState();

    // WebSocket Subscriptions
    const wsFeed = new WebSocket('ws://localhost:8000/ws/live_feed');
    wsFeed.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      // Clear the feed if the reset signal is received
      if (data.clear) {
        setFeed([]);
      } else {
        // Prepend new trade and keep max 100
        setFeed(prev => [data, ...prev].slice(0, 100)); 
      }
    };

    const wsSummary = new WebSocket('ws://localhost:8000/ws/summary');
    wsSummary.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data?.account) setAccountBalance(data.account.balance);
    };

    const wsPositions = new WebSocket('ws://localhost:8000/ws/positions');
    wsPositions.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const positionsArray = Array.isArray(data) ? data : (data.positions || []);
      setInvestedValue(positionsArray.reduce((sum: number, pos: any) => sum + (pos.cost_basis || 0), 0));
    };

    // Cleanup on unmount
    return () => {
      wsFeed.close();
      wsSummary.close();
      wsPositions.close();
    };
  }, []);

  const totalAccountValue = accountBalance !== null ? accountBalance + investedValue : null;

  return (
    <Box sx={{ p: 4 }}>
      
      {/* Header Area */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 3 }}>
        <Typography variant="h5" sx={{ fontWeight: 'bold' }}>Live Trading Feed</Typography>
        <Box sx={{ textAlign: 'right' }}>
          {totalAccountValue !== null && (
            <Typography variant="h6" sx={{ fontWeight: 'bold' }}>
              Account Value: ${totalAccountValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </Typography>
          )}
          {accountBalance !== null && (
            <Typography variant="subtitle1" sx={{ color: '#4caf50', fontFamily: 'monospace' }}>
              Available Cash: ${accountBalance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </Typography>
          )}
        </Box>
      </Box>

      {/* Feed List */}
      <List>
        {feed.map((trade, i) => (
          <ListItem key={i} component={Paper} sx={{ mb: 2, p: 2, bgcolor: '#000000e4', borderRadius: 2, 
            borderLeft: `1px solid ${trade.side === 'BUY' ? '#2e7d32' : '#c62828'}`,
            borderRight: (trade.side === 'SELL' && trade.realised_pnl !== null) 
              ? `1px solid ${trade.realised_pnl > 0 ? '#4caf50' : '#f44336'}` 
              : 'none'
          }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', width: '100%', alignItems: 'center' }}>
              
              {/* Left Column: Asset & Time */}
              <Box sx={{ minWidth: '200px' }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Chip
                    label={trade.side}
                    size="small"
                    sx={{ bgcolor: trade.side === 'BUY' ? '#1b5e20' : '#b71c1c', color: 'white', fontWeight: 'bold' }}
                  />
                  {trade.symbol}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                  {new Date(trade.timestamp).toLocaleTimeString()} | Whale: {trade.wallet_address.slice(0, 6)}...{trade.wallet_address.slice(-4)}
                </Typography>
              </Box>

              {/* Middle Column: Volume & Price */}
              <Box sx={{ flex: 1, textAlign: 'center' }}>
                 <Typography variant="body1" sx={{ fontFamily: 'monospace' }}>
                   {trade.amount.toLocaleString(undefined, { maximumFractionDigits: 4 })} @ ${trade.price.toFixed(6)}
                 </Typography>
                 <Typography variant="body2" color="text.secondary">
                   Total Value: ${trade.usd_value.toFixed(2)}
                 </Typography>
              </Box>

              {/* Right Column: Outcomes (Sells only) */}
              <Box sx={{ textAlign: 'right', minWidth: '150px' }}>
                {trade.side === 'SELL' && (
                  <>
                    {trade.sell_reason && (
                      <Chip label={trade.sell_reason.replace('_', ' ')} size="small" variant="outlined" sx={{ mb: 0.5, borderColor: '#555' }} />
                    )}
                    {trade.realised_pnl !== null && (
                      <Typography variant="body2" sx={{ color: trade.realised_pnl > 0 ? '#4caf50' : '#f44336', fontWeight: 'bold' }}>
                        PnL: {trade.realised_pnl > 0 ? '+' : ''}${trade.realised_pnl.toFixed(2)}
                      </Typography>
                    )}
                  </>
                )}
              </Box>

            </Box>
          </ListItem>
        ))}
        {feed.length === 0 && (
          <Typography color="text.secondary" sx={{ textAlign: 'center', mt: 4 }}>Listening for engine activity...</Typography>
        )}
      </List>
    </Box>
  );
}