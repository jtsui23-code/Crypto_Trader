import React, { useState, useEffect } from 'react';
import { Box, Typography, Grid, Paper, Skeleton } from '@mui/material';
import { PieChart } from '@mui/x-charts/PieChart';

export const AnalyticsView = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [forecastTimestamp, setForecastTimestamp] = useState<number>(Date.now());
  const API_BASE_URL = "http://localhost:8000";

  useEffect(() => {
    // Fetch Analytics Summary
    fetch(`${API_BASE_URL}/api/analytics/summary`)
      .then(res => res.json())
      .then(json => {
        setData(json);
        setLoading(false);
      })
      .catch(err => {
        console.error("Analytics fetch error:", err);
        setLoading(false);
      });

    // LSTM Image refresh interval
    const interval = setInterval(() => {
      setForecastTimestamp(Date.now());
    }, 600000); 

    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <Box sx={{ p: 4 }}>
        <Skeleton variant="text" width={300} height={60} sx={{ mb: 4 }} />
        <Grid container spacing={3}>
          {[1, 2, 3].map((i) => (
            <Grid item xs={12} md={4} key={i}>
              <Skeleton variant="rectangular" height={280} sx={{ borderRadius: 2 }} />
            </Grid>
          ))}
        </Grid>
      </Box>
    );
  }

  if (!data || data.error || !data.account) {
    return (
      <Box sx={{ p: 4, textAlign: 'center' }}>
        <Typography color="error">
          {data?.error || "Failed to load account data. Ensure the backend endpoint is active."}
        </Typography>
      </Box>
    );
  }

  const initial = data.account.initial || 1;
  const balance = data.account.balance || 0;
  const drawdown = (((initial - balance) / initial) * 100).toFixed(2);

  const cardStyle = {
    p: 2,
    border: '1px solid #333',
    bgcolor: 'background.paper',
    height: 280,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center'
  };

  return (
    <Box sx={{ p: 4 }}>
      {/* Header section with Title and Timestamp */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
        <Typography variant="h4" sx={{ color: '#208dd1' }}>System Analytics</Typography>
        <Box sx={{ px: 2, py: 1, bgcolor: '#1e1e1e', borderRadius: 2, border: '1px solid #333' }}>
          <Typography variant="caption" color="text.secondary">Last Update: </Typography>
          <Typography variant="body2" component="span" sx={{ fontFamily: 'monospace' }}>
            {new Date(forecastTimestamp).toLocaleTimeString()}
          </Typography>
        </Box>
      </Box>

      <Grid container spacing={3}>
        {/* Top Row: System Dashboard */}
        <Grid item xs={12} md={4}>
          <Paper variant="outlined" sx={cardStyle}>
            <Box sx={{ textAlign: 'center' }}>
              <Typography variant="overline" color="text.secondary">Current Balance</Typography>
              <Typography variant="h3" sx={{ my: 1 }}>${balance.toLocaleString()}</Typography>
              <Typography variant="body2" sx={{ color: '#f87171' }}>
                Max Drawdown: {drawdown}%
              </Typography>
            </Box>
          </Paper>
        </Grid>

        <Grid item xs={12} md={4}>
          <Paper variant="outlined" sx={cardStyle}>
            <Typography variant="overline" color="text.secondary" sx={{ mb: 2 }}>
              Exit Strategy Breakdown
            </Typography>
            <PieChart
              series={[{
                data: data.exit_reasons || [],
                innerRadius: 50,
                paddingAngle: 2,
                cornerRadius: 4,
              }]}
              height={180}
              width={180}
              slotProps={{ legend: { hidden: true } }}
            />
          </Paper>
        </Grid>

        <Grid item xs={12} md={4}>
          <Paper variant="outlined" sx={cardStyle}>
            <Typography variant="overline" color="text.secondary" sx={{ mb: 2 }}>
              Token Concentration
            </Typography>
            <PieChart
              series={[{
                data: data.exposure || [],
                innerRadius: 50,
                paddingAngle: 2,
                cornerRadius: 4,
              }]}
              height={180}
              width={180}
              slotProps={{ legend: { hidden: true } }}
            />
          </Paper>
        </Grid>

        {/* Bottom Row: LSTM Forecast Chart */}
        <Grid item xs={12}>
          <Paper variant="outlined" sx={{ p: 3, border: '1px solid #333', bgcolor: 'background.paper', borderRadius: 2 }}>
            <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
              {/* Pulse indicator */}
              <Box sx={{ width: 10, height: 10, bgcolor: '#22c55e', borderRadius: '50%', animation: 'pulse 2s infinite' }} />
              SOL/USD LSTM Price Forecast (14-Day)
            </Typography>
            
            <Box sx={{ position: 'relative', overflow: 'hidden', borderRadius: 2, bgcolor: '#000', display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 450 }}>
              <img 
                src={`${API_BASE_URL}/plots/solana_lstm_forecast.png?t=${forecastTimestamp}`}
                alt="LSTM Prediction Chart"
                style={{ maxWidth: '100%', height: 'auto' }}
                onError={(e) => {
                  const target = e.target as HTMLImageElement;
                  target.src = 'https://via.placeholder.com/800x450?text=Waiting+for+LSTM+Generator...';
                }}
              />
            </Box>
          </Paper>
        </Grid>

      </Grid>
    </Box>
  );
};