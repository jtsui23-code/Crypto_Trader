// src/App.tsx
import { useState, useEffect } from 'react';
import { Box, List, Typography, CssBaseline } from '@mui/material';
import { TraderListItem } from './components/TraderListItem';
import { TraderDetailView } from './components/TraderDetailView';

interface Trader {
  id: string;
  name: string;
  record: string;
}

export default function App() {
  const [selectedTraderId, setSelectedTraderId] = useState<string | null>(null);
  const [traders, setTraders] = useState<Trader[]>([]);

  useEffect(() => {
    // UPDATED: Fetch from your backend API instead of local JSON
    fetch('http://localhost:8000/api/traders')
      .then((res) => res.json())
      .then((data) => {
        // Handle cases where the API might return { "wallets": [...] }
        const traderArray = Array.isArray(data) ? data : (data.wallets || []);
        setTraders(traderArray);
      })
      .catch((err) => console.error("Error loading traders:", err));
  }, []);

  const selectedTrader = traders.find((t) => t.id === selectedTraderId);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh', bgcolor: '#0a0a0a', color: 'white' }}>
      <CssBaseline />
      <Box sx={{ p: 2, borderBottom: '1px solid #333' }}>
        <Typography variant="h6" sx={{ color: 'cyan' }}>Targeted Wallets Tracker</Typography>
      </Box>

      <Box sx={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <Box sx={{ width: 350, borderRight: '1px solid #333', overflowY: 'auto' }}>
          <List>
            {traders.map((trader) => (
              <TraderListItem 
                key={trader.id} 
                name={trader.name} 
                record={trader.record}
                isSelected={selectedTraderId === trader.id}
                onSelect={() => setSelectedTraderId(trader.id)}
              />
            ))}
          </List>
        </Box>
        <Box sx={{ flex: 1, overflowY: 'auto' }}>
          <TraderDetailView trader={selectedTrader} />
        </Box>
      </Box>
    </Box>
  );
}