import React, { useState, useEffect } from 'react';
import { Box, Typography, Grid, Paper, Skeleton, Stack } from '@mui/material';
import { PieChart } from '@mui/x-charts/PieChart';
import { LineChart } from '@mui/x-charts/LineChart';

export const AnalyticsView = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  
  // Track the timestamp to show the last update time
  const [forecastTimestamp, setForecastTimestamp] = useState<number>(Date.now());
  
  // New state to hold the raw LSTM JSON data
  const [lstmChartData, setLstmChartData] = useState<any[] | null>(null);
  
  const API_BASE_URL = "http://localhost:8000";

  useEffect(() => {
    // 1. Initial fetch to populate data and turn off the loading skeleton
    fetch(`${API_BASE_URL}/api/analytics/summary`)
      .then(res => res.json())
      .then(fetchedData => {
        setData(fetchedData);
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to fetch analytics:", err);
        setLoading(false);
      });

    // 2. WebSocket for Analytics Summary (Pie Charts & Balance)
    const wsSummary = new WebSocket('ws://localhost:8000/ws/summary');
    wsSummary.onmessage = (event) => {
      const updatedAnalytics = JSON.parse(event.data);
      setData(updatedAnalytics); 
    };

    // 3. WebSocket for LSTM Forecast Data
    const wsForecast = new WebSocket('ws://localhost:8000/ws/forecast');
    wsForecast.onmessage = (event) => {
      const wsData = JSON.parse(event.data);
      if (wsData?.chart_data) {
        setLstmChartData(wsData.chart_data);
        setForecastTimestamp(Date.now());
      }
    };

    return () => {
      wsSummary.close();
      wsForecast.close();
    };
  }, []);

  let forecastColor = '#f59e0b'; // Default orange
  if (lstmChartData && lstmChartData.length > 0) {
    const firstForecast = lstmChartData.find(d => d.predicted !== null)?.predicted;
    const lastForecast = lstmChartData[lstmChartData.length - 1]?.predicted;
    
    if (firstForecast !== undefined && lastForecast !== undefined) {
      // Green if trending up or flat, Red if trending down
      forecastColor = lastForecast >= firstForecast ? '#4caf50' : '#f87171';
    }
  }

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
  const pnl = balance - initial;
  const pnlPercent = initial > 0 ? ((pnl / initial) * 100).toFixed(2) : "0.00";

  const cardStyle = {
    p: 2,
    border: 1, borderColor: 'divider',
    bgcolor: 'background.paper',
    height: 280,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center'
  };

  const pnlData = data.pnl_history || [];
  const hasPnlData = pnlData.length > 0;
  const xAxisData = pnlData.map((d: any) => new Date(d.time));
  const yAxisData = pnlData.map((d: any) => d.pnl);

  return (
    <Box sx={{ p: 4 }}>
      {/* Header section with Title and Timestamp */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
        <Typography variant="h4" sx={{ color: 'primary.main' }}>System Analytics</Typography>
        <Box sx={{ px: 2, py: 1, bgcolor: 'background.paper', borderRadius: 2, border: 1, borderColor: 'divider' }}>
          <Typography variant="caption" color="text.secondary">Last Update: </Typography>
          <Typography variant="body2" component="span" sx={{ fontFamily: 'monospace' }}>
            {new Date(forecastTimestamp).toLocaleTimeString()}
          </Typography>
        </Box>
      </Box>

      {/* Force explicit vertical rows using Stack */}
      <Stack spacing={3}>

        {/* ============================== */}
        {/* ROW 1: The Three Top Cards     */}
        {/* ============================== */}
        <Grid container spacing={3}>
          {/* Top Row: System Dashboard */}
          <Grid item xs={12} md={4}>
            <Paper variant="outlined" sx={cardStyle}>
              <Box sx={{ textAlign: 'center' }}>
                <Typography variant="overline" color="text.secondary">Current Balance</Typography>
                <Typography variant="h3" sx={{ my: 1 }}>
                  ${balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Start Balance: ${initial.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </Typography>
                <Typography variant="body2" sx={{ color: pnl >= 0 ? 'success.main' : 'error.main', fontWeight: 'bold', mt: 0.5 }}>
                  {pnl >= 0 ? '+' : ''}${pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ({pnlPercent}%)
                </Typography>
              </Box>
            </Paper>
          </Grid>

          {/* Top Row: Exit strategy breakdown */}
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
              
          {/* Top Row: Token concentration */}
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
        </Grid>
        
        {/* ============================== */}
        {/* ROW 2: PnL Chart               */}
        {/* ============================== */}
        <Paper variant="outlined" sx={{ p: 3, border: 1, borderColor: 'divider', bgcolor: 'background.paper', borderRadius: 2 }}>
          <Typography variant="overline" color="text.secondary" sx={{ mb: 2, display: 'block', textAlign: 'center', fontSize: '1rem' }}>
            Cumulative PnL Performance
          </Typography>
          {hasPnlData ? (
            <Box sx={{ width: '100%', height: 350 }}>
              <LineChart
                xAxis={[{ 
                  data: xAxisData, 
                  scaleType: 'point',
                  valueFormatter: (date) => date.toLocaleDateString() 
                }]}
                series={[{ 
                  data: yAxisData, 
                  label: 'Total PnL ($)',
                  showMark: false,
                  area: false,
                  color: 'var(--accent-color)'
                }]}
                margin={{ top: 20, bottom: 30, left: 50, right: 20 }}
              />
            </Box>
          ) : (
            <Box sx={{ height: 350, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Typography color="text.secondary">No PnL history available yet.</Typography>
            </Box>
          )}
        </Paper>

        {/* ============================== */}
        {/* ROW 3: LSTM Forecast Chart     */}
        {/* ============================== */}
        <Paper variant="outlined" sx={{ p: 3, border: 1, borderColor: 'divider', bgcolor: 'background.paper', borderRadius: 2 }}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
            SOL/USD LSTM Price Forecast (14-Day)
          </Typography>
          
          {lstmChartData ? (
            <Box sx={{ width: '100%', height: 450 }}>
              <LineChart
                dataset={lstmChartData}
                xAxis={[{ 
                  dataKey: 'date', 
                  scaleType: 'point',
                  valueFormatter: (val) => new Date(val).toLocaleDateString()
                }]}
                series={[
                  { dataKey: 'actual', label: 'Historical ($)', color: 'var(--accent-color)', showMark: false },
                  { dataKey: 'predicted', label: 'Forecast ($)', color: forecastColor, showMark: false }
                ]}
                margin={{ top: 20, bottom: 30, left: 50, right: 20 }}
              />
            </Box>
          ) : (
            <Box sx={{ height: 450, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Typography color="text.secondary">Waiting for LSTM Generator data...</Typography>
            </Box>
          )}
        </Paper>

      </Stack>
    </Box>
  );
};