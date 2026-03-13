import { useState, useEffect } from 'react';
import { Box, List, Typography, CssBaseline } from '@mui/material';
import { CoinListItem } from './components/CoinListItem';
import { CoinDetailView } from './components/CoinDetailView';
import { TraderListItem } from './components/TraderListItem';
import { TraderDetailView } from './components/TraderDetailView';

// Define TypeScript interfaces to match your JSON structure
interface Coin {
  id: string;
  name: string;
  symbol: string;
  price: string;
}

interface Trader {
  id: string;
  name: string;
  record: string;
}

export default function App() {
  // 1. View and Selection State
  const [activeTab, setActiveTab] = useState<'portfolio' | 'traders'>('portfolio');
  const [selectedCoinId, setSelectedCoinId] = useState<string>('1');
  const [selectedTraderId, setSelectedTraderId] = useState<string | null>(null);

  // 2. Data State
  const [coins, setCoins] = useState<Coin[]>([]);
  const [traders, setTraders] = useState<Trader[]>([]);

  // 3. Fetch Data from JSON files on load
  useEffect(() => {
    fetch('/data/coins.json')
      .then((res) => res.json())
      .then((data) => setCoins(data))
      .catch((err) => console.error("Error loading coins:", err));

    fetch('/data/traders.json')
      .then((res) => res.json())
      .then((data) => setTraders(data))
      .catch((err) => console.error("Error loading traders:", err));
  }, []);

  // 4. Derived Data for Detail Views
  const selectedCoin = coins.find((c) => c.id === selectedCoinId);
  const selectedTrader = traders.find((t) => t.id === selectedTraderId);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <CssBaseline />
      
      {/* Navbar */}
      <Box sx={{ p: 2, borderBottom: '1px solid #333', display: 'flex', gap: 4 }}>
        <Typography 
          onClick={() => setActiveTab('portfolio')}
          sx={{ 
            cursor: 'pointer', 
            color: activeTab === 'portfolio' ? 'cyan' : '#9ca3af',
            fontWeight: activeTab === 'portfolio' ? 'bold' : 'normal',
            transition: 'color 0.2s'
          }}
        >
          Portfolio
        </Typography>
        <Typography 
          onClick={() => setActiveTab('traders')}
          sx={{ 
            cursor: 'pointer', 
            color: activeTab === 'traders' ? 'cyan' : '#9ca3af',
            fontWeight: activeTab === 'traders' ? 'bold' : 'normal',
            transition: 'color 0.2s'
          }}
        >
          Top Traders
        </Typography>
      </Box>

      {/* Content Area */}
      <Box sx={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        
        {/* Dynamic Sidebar */}
        <Box sx={{ width: 300, borderRight: '1px solid #333', overflowY: 'auto' }}>
          <Typography variant="overline" sx={{ p: 2, display: 'block', textAlign: 'center' }}>
            {activeTab === 'portfolio' ? 'Owned Assets' : 'Followed Traders'}
          </Typography>
          
          <List>
            {activeTab === 'portfolio' ? (
              coins.map((coin) => (
                <CoinListItem 
                  key={coin.id}
                  {...coin}
                  isSelected={selectedCoinId === coin.id}
                  onSelect={() => setSelectedCoinId(coin.id)}
                />
              ))
            ) : (
              traders.map((trader) => (
                <TraderListItem 
                  key={trader.id} 
                  name={trader.name} 
                  record={trader.record}
                  isSelected={selectedTraderId === trader.id}
                  onSelect={() => setSelectedTraderId(trader.id)}
                />
              ))
            )}
          </List>
        </Box>

        {/* Dynamic Detail View */}
        <Box sx={{ flex: 1, overflowY: 'auto' }}>
          {activeTab === 'portfolio' ? (
            <CoinDetailView coin={selectedCoin} />
          ) : (
            <TraderDetailView trader={selectedTrader} />
          )}
        </Box>

      </Box>
    </Box>
  );
}