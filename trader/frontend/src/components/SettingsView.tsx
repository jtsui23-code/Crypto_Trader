import { useState, useEffect, useRef } from 'react';
import { Box, Typography, TextField, Button, Grid, Paper, Tooltip, CircularProgress } from '@mui/material';

const THEME_KEYS = [
  { id: '--bg-color', label: 'App Background' },
  { id: '--nav-bg', label: 'Top Bar Background' },
  { id: '--text-color', label: 'Primary Text' },
  { id: '--accent-color', label: 'Accent Color' },
  { id: '--card-bg', label: 'Card Background' }
];

function ThemeColorPicker({ 
  id, 
  label, 
  value, 
  onApply 
}: { 
  id: string; 
  label: string; 
  value: string; 
  onApply: (id: string, value: string) => void;
}) {
  const parseColor = (val: string) => {
    let hex = val.startsWith('#') ? val : '#000000';
    let alpha = 1;
    if (hex.length === 9) { // Has alpha channel
      alpha = parseInt(hex.slice(7, 9), 16) / 255;
      hex = hex.slice(0, 7);
    }
    return { hex, alpha };
  };

  const [textValue, setTextValue] = useState(value);
  const [colorState, setColorState] = useState(parseColor(value));
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setTextValue(value);
    setColorState(parseColor(value));
  }, [value]);

  const handleUpdate = (newBase: string, newAlpha: number, isFinalSave: boolean) => {
    const alphaHex = Math.round(newAlpha * 255).toString(16).padStart(2, '0');
    const finalColor = newAlpha === 1 ? newBase : `${newBase}${alphaHex}`;

    setColorState({ hex: newBase, alpha: newAlpha });
    setTextValue(finalColor);
    document.documentElement.style.setProperty(id, finalColor);

    if (isFinalSave) {
      onApply(id, finalColor);
    }
  };

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    
    const handleNativeChange = (e: Event) => {
      const target = e.target as HTMLInputElement;
      handleUpdate(target.value, colorState.alpha, true);
    };
    
    el.addEventListener('change', handleNativeChange);
    return () => el.removeEventListener('change', handleNativeChange);
  }, [id, colorState.alpha, onApply]);

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '8px' }}>
      <Typography sx={{ width: '150px' }}>{label}</Typography>
      
      <input
        ref={inputRef}
        type="color"
        id={id}
        value={colorState.hex} 
        onChange={(e) => handleUpdate(e.target.value, colorState.alpha, false)}
        style={{ cursor: 'pointer', padding: '0', border: 'none', background: 'none', height: '32px', width: '32px' }}
      />

      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', width: '120px' }}>
        <input
          type="range"
          min="0"
          max="1"
          step="0.01"
          value={colorState.alpha}
          onChange={(e) => handleUpdate(colorState.hex, parseFloat(e.target.value), false)}
          onMouseUp={() => handleUpdate(colorState.hex, colorState.alpha, true)}
          onTouchEnd={() => handleUpdate(colorState.hex, colorState.alpha, true)}
          style={{ width: '70px', cursor: 'pointer' }}
        />
        <Typography variant="body2" sx={{ color: 'text.secondary', minWidth: '35px' }}>
          {Math.round(colorState.alpha * 100)}%
        </Typography>
      </div>

      <TextField 
        variant="outlined"
        size="small"
        value={textValue}
        onChange={(e) => {
          const val = e.target.value;
          setTextValue(val);
          
          if (/^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$/.test(val)) {
            const parsed = parseColor(val);
            setColorState(parsed);
            document.documentElement.style.setProperty(id, val);
          }
        }}
        onBlur={(e) => {
          const val = e.target.value;
          if (/^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$/.test(val)) {
            const parsed = parseColor(val);
            handleUpdate(parsed.hex, parsed.alpha, true);
          } else {
            const revertedHex = colorState.alpha === 1 
              ? colorState.hex 
              : `${colorState.hex}${Math.round(colorState.alpha * 255).toString(16).padStart(2, '0')}`;
            setTextValue(revertedHex);
          }
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') e.currentTarget.blur();
        }}
        sx={{ width: '130px' }}
        inputProps={{ 
          style: { fontFamily: 'monospace', padding: '8px 12px' } 
        }}
      />
    </div>
  );
}

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

    // Fetch config — merge so any keys missing from the server response
    // (e.g. dex_fee_pct on older saved configs) fall back to the defaults above.
    fetch('http://localhost:8000/api/settings/config')
      .then(res => res.json())
      .then(data => setConfig(prev => ({ ...prev, ...data })))
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

  const [colors, setColors] = useState<Record<string, string>>({});

  useEffect(() => {
    const savedColors = JSON.parse(localStorage.getItem('themeColors') || '{}');
    const root = document.documentElement;
    const initialColors: Record<string, string> = {};

    THEME_KEYS.forEach(({ id }) => {
      if (savedColors[id]) {
        initialColors[id] = savedColors[id];
      } else {
        // Fallback to the CSS variable default if nothing is in localStorage
        initialColors[id] = getComputedStyle(root).getPropertyValue(id).trim() || '#000000';
      }
    });
    setColors(initialColors);
  }, []);

  const handleColorChange = (id: string, value: string) => {
    // 1. Instant UI updates for zero visual lag
    setColors(prev => ({ ...prev, [id]: value }));
    document.documentElement.style.setProperty(id, value);
    
    // 2. Defer the heavy MUI rebuild and disk save by 10ms
    // This allows the OS color picker dialog to close instantly
    setTimeout(() => {
      const currentSaved = JSON.parse(localStorage.getItem('themeColors') || '{}');
      localStorage.setItem('themeColors', JSON.stringify({ ...currentSaved, [id]: value }));
      window.dispatchEvent(new Event('themeChanged'));
    }, 10);
  };

  const handleColorReset = () => {
    // 1. Clear saved colors from storage
    localStorage.removeItem('themeColors');
    
    // 2. Remove inline styles so the app falls back to your index.css defaults
    const root = document.documentElement;
    THEME_KEYS.forEach(({ id }) => root.style.removeProperty(id));

    // 3. Read the default CSS values and update the color pickers' visual state
    const defaultColors: Record<string, string> = {};
    THEME_KEYS.forEach(({ id }) => {
      defaultColors[id] = getComputedStyle(root).getPropertyValue(id).trim() || '#000000';
    });
    setColors(defaultColors);

    // 4. Tell App.tsx to rebuild the Material-UI theme
    window.dispatchEvent(new Event('themeChanged'));
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
      <h2>Theme Settings</h2>
      
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {THEME_KEYS.map(({ id, label }) => (
          <ThemeColorPicker
            key={id}
            id={id}
            label={label}
            value={colors[id] || '#000000'}
            onApply={handleColorChange}
          />
        ))}
      </div>
      <button onClick={handleColorReset} style={{ marginTop: '24px' }}>Reset Color Defaults</button>
      </Box>
    </Box>
  );
}