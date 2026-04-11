import { Box, Typography, Grid, Paper, Skeleton } from '@mui/material';
import { PieChart } from '@mui/x-charts/PieChart';
import { useEffect, useState } from 'react';

// AnalyticsView component for displaying overall system analytics and performance metrics
export const AnalyticsView = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('http://localhost:8000/api/analytics/summary')
      .then(res => res.json())
      .then(json => {
        setData(json);
        setLoading(false);
      })
      .catch(err => {
        console.error("Analytics fetch error:", err);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <Box sx={{ p: 4 }}>
        <Skeleton variant="text" width={300} height={60} sx={{ mb: 4 }} />
        <Grid container spacing={3}>
          {[1, 2, 3].map((i) => (
            <Grid item xs={4} key={i}>
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
    height: 280, // Fixed height for consistency
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center'
  };

  return (
    <Box sx={{ p: 4 }}>
      <Typography variant="h4" sx={{ color: '#208dd1', mb: 4 }}>System Analytics</Typography>

      <Grid container spacing={3}>
        {/* Current Balance Card */}
        <Grid item xs={4}>
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

        {/* Exit Strategy Breakdown */}
        <Grid item xs={4}>
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
              width={250}
              slotProps={{ legend: { hidden: true } }}
            />
          </Paper>
        </Grid>

        {/* Token Concentration */}
        <Grid item xs={4}>
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
              width={300}
              slotProps={{ legend: { hidden: true } }}
            />
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};