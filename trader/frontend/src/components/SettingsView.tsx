import { useState, useEffect } from 'react';
import { Box, Typography, TextField, Button, Grid, Paper, Tooltip, CircularProgress } from '@mui/material';

export function SettingsView() {
  const [whales, setWhales] = useState<string>('');
  const [balance, setBalance] = useState<number>(10000);
  const [config, setConfig] = useState({
    risk_per_trade: 0.05,
    take_profit_pct: 0.2,
    take_profit_split: 0.7,
    trailing_stop_pct: 0.35,
    stop_loss_pct: 0.15,
    max_hold_seconds: 70,
    dex_fee_pct: 0.0025
  });

  const [isResetting, setIsResetting] = useState(false);
  const [isSavingWhales, setIsSavingWhales] = useState(false);

  const PARAM_DESCRIPTIONS: Record<string, string> = {
    risk_per_trade: "The fraction of your total balance to risk on a single trade (e.g., 0.05 = 5%).",
    take_profit_pct: "The price percentage increase from entry that triggers a partial sell.",
    take_profit_split: "The portion of the position to sell when the take profit target is hit (e.g., 0.7 = 70%).",
    trailing_stop_pct: "The max percentage price drop allowed from the peak before a full exit.",
    stop_loss_pct: "The max percentage loss allowed from the entry price before a full exit.",
    max_hold_seconds: "The maximum duration to hold a position before it is automatically sold.",
    dex_fee_pct: "The DEX trading fee charged per swap on Solana (e.g., 0.0025 = 0.25%). Applied to both buys and sells to simulate real costs. Raydium/Jupiter default is 0.25%."
  };


  useEffect(() => {
    // Fetch whales
    fetch('http://localhost:8000/api/settings/whales')
      .then(res => res.json())
      .then(data => setWhales(data.wallets.join('\n')))
      .catch(console.error);      

    // Fetch config
    fetch('http://localhost:8000/api/settings/config')
      .then(res => res.json())
      .then(data => setConfig(data))
      .catch(console.error);
  }, []);


  const handleWhaleSave = async () => {
    setIsSavingWhales(true);
    try {
          const uniqueWallets = Array.from(
            new Set(whales.split('\n').map(w => w.trim()).filter(w => w))
          );

          setWhales(uniqueWallets.join('\n'));

          await fetch('http://localhost:8000/api/settings/whales', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ wallets: uniqueWallets })
          });
          alert('Whales updated successfully');
    } catch (error) {
      console.error(error);
      alert('Failed to update whales');
    } finally {
      setIsSavingWhales(false);
    }
  };

  const handleConfigSave = async () => {
    await fetch('http://localhost:8000/api/settings/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    });
    alert('Engine configuration updated');
  };

  const handleReset = async () => {
    setIsResetting(true); // Start animation
    try {
      await fetch('http://localhost:8000/api/engine/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_balance: balance })
      });
      alert(`Engine reset triggered with balance: $${balance}`);
    } catch (error) {
      console.error(error);
      alert('Failed to reset engine');
    } finally {
      setIsResetting(false); 
    }
  };


  return (
    <Box sx={{ p: 3, width: '100%' }}>
      <Typography variant="h4" sx={{ mb: 4 }}>Settings</Typography>
      
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {/* Whales Editor */}
        <Grid item xs={12} md={12}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" sx={{ mb: 2 }}>Target Wallets</Typography>
            <TextField
              multiline
              rows={10}
              fullWidth
              variant="outlined"
              value={whales}
              disabled={isSavingWhales} // Disable input while saving
              onChange={(e) => setWhales(e.target.value)}
              placeholder="Enter wallet addresses (one per line)"
              sx={{ mb: 2 }}
              inputProps={{ 
                style: { fontFamily: 'monospace' } 
              }}
            />
            <Button 
              variant="contained" 
              onClick={handleWhaleSave} 
              sx={{ width: '200px' }}
              disabled={isSavingWhales} // Disable button while saving
              startIcon={isSavingWhales ? <CircularProgress size={20} color="inherit" /> : null}
            >
              {isSavingWhales ? 'Saving...' : 'Save Wallets'}
            </Button>
          </Paper>
        </Grid>

      {/* Engine Config */}
      <Grid item xs={12} md={6}>
        <Paper sx={{ p: 3, height: '100%' }}>
          <Typography variant="h6" sx={{ mb: 2 }}>Trading Parameters</Typography>
          {Object.entries(config).map(([key, value]) => (
            <Tooltip 
              key={key} 
              title={PARAM_DESCRIPTIONS[key] || ""} 
              placement="left" 
              arrow
            >
              <TextField
                label={key.replace(/_/g, ' ').toUpperCase()}
                type="number"
                fullWidth
                value={value}
                onChange={(e) => setConfig({ ...config, [key]: parseFloat(e.target.value) })}
                sx={{ mb: 2 }}
                inputProps={{ step: "0.01" }}
              />
            </Tooltip>
          ))}
          <Button variant="contained" onClick={handleConfigSave} fullWidth>
            Save Configuration
          </Button>
        </Paper>
      </Grid>

      {/* Engine Reset */}
      <Grid item xs={12} md={6}>
        <Paper sx={{ p: 3, height: '100%' }}>
          <Typography variant="h6" sx={{ mb: 2 }}>Reset Engine</Typography>
          <Typography variant="body2" sx={{ mb: 2, color: 'text.secondary' }}>
            Wipes open positions, trade history, and resets the paper account balance.
          </Typography>
          <TextField
            label="Starting Balance (USD)"
            type="number"
            fullWidth
            disabled={isResetting} // Disable input during reset
            value={balance}
            onChange={(e) => setBalance(parseFloat(e.target.value))}
            sx={{ mb: 2 }}
          />
          <Button 
            variant="outlined" 
            color="error" 
            onClick={handleReset} 
            fullWidth
            disabled={isResetting} // Disable button to prevent double-clicks
            startIcon={isResetting ? <CircularProgress size={20} color="inherit" /> : null}
          >
            {isResetting ? 'Resetting...' : 'Execute Reset'}
          </Button>
        </Paper>
      </Grid>
      </Box>
    </Box>
  );
}