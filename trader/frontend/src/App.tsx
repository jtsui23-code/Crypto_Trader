import { useState, useEffect } from 'react';
import { Box, List, Typography, CssBaseline, Button } from '@mui/material';
import { ThemeProvider, createTheme } from '@mui/material/styles';

import { CoinListItem } from './components/CoinListItem';
import { CoinDetailView } from './components/CoinDetailView';

import { TraderListItem } from './components/TraderListItem';
import { TraderDetailView } from './components/TraderDetailView';

import { AnalyticsView } from './components/AnalyticsView';

interface Coin {
  id: string;
  symbol: string;
  amount: number;
  entry_price: number;
  peak_price: number;
  cost_basis: number;
  wallet_address: string;
}

interface Trader {
  id: string;
  name: string;
  record: string;
  winning_trades: number;
  losing_trades: number;
  best_trade_pnl: number;
  worst_trade_pnl: number;
  avg_pnl_per_trade: number;
  total_pnl: number;
}

const backgroundColor = '#0a0a0a';
const activeColor = '#208dd1';
const inactiveColor = '#115e8f';
const updateIntervalMs = 10000;

const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    background: {
      default: '#0a0a0a',
      paper: '#1a1a1a',
    },
    text: {
      primary: '#ffffff',
      secondary: '#9e9e9e',
    },
  },
  components: {
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
        },
      },
    },
  },
});

export default function App() {
  // State for tab management
  const [activeTab, setActiveTab] = useState<'portfolio' | 'traders' | 'analytics'>('portfolio');
  const [selectedCoinId, setSelectedCoinId] = useState<string | null>(null);
  const [selectedTraderId, setSelectedTraderId] = useState<string | null>(null);

  // Data states
  const [coins, setCoins] = useState<Coin[]>([]);
  const [traders, setTraders] = useState<Trader[]>([]);

  // Sorting statess
  const [traderSort, setTraderSort] = useState<'desc' | 'asc'>('desc');
  const [coinSort, setCoinSort] = useState<'desc' | 'asc'>('desc');

  // Fetch functions
  const fetchTraders = () => {
    fetch('http://localhost:8000/api/traders')
      .then((res) => res.json())
      .then((data) => {
        const traderArray = Array.isArray(data) ? data : (data.wallets || []);
        setTraders(traderArray);
      })
      .catch(console.error);
  };

  const fetchCoins = () => {
    fetch('http://localhost:8000/api/portfolio/positions')
      .then((res) => res.json())
      .then((data) => {
        const coinsArray = Array.isArray(data) ? data : (data.positions || []);
        setCoins(coinsArray);
        if (coinsArray.length > 0 && !selectedCoinId) setSelectedCoinId(coinsArray[0].id);
      })
      .catch(console.error);
  };

  // Initial data fetch and setup auto-refresh
  useEffect(() => {
    fetchCoins();
    fetchTraders();
    const intervalId = setInterval(() => {
      fetchCoins();
      fetchTraders();
    }, updateIntervalMs);
    return () => clearInterval(intervalId);
  }, []);

  // Sorting logic
  const sortedTraders = [...traders].sort((a, b) => {
    const pnlA = a.total_pnl || 0;
    const pnlB = b.total_pnl || 0;
    return traderSort === 'desc' ? pnlB - pnlA : pnlA - pnlB;
  });

  const sortedCoins = [...coins].sort((a, b) => {
    const priceA = a.entry_price || 0;
    const priceB = b.entry_price || 0;
    return coinSort === 'desc' ? priceB - priceA : priceA - priceB;
  });
 
  // Find selected items
  const selectedCoin = coins.find((c) => c.id === selectedCoinId);
  const selectedTrader = traders.find((t) => t.id === selectedTraderId);

  // Render
  return (
    <ThemeProvider theme={darkTheme}>
      <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
        <CssBaseline />

        {/* Navigation Tabs */}
        <Box sx={{ p: 2, borderBottom: '1px solid #333', display: 'flex', gap: 6 }}>
          {['portfolio', 'traders', 'analytics'].map((tab) => (
            <Typography
              key={tab}
              onClick={() => setActiveTab(tab as any)}
              sx={{
                cursor: 'pointer',
                textTransform: 'capitalize',
                color: activeTab === tab ? activeColor : inactiveColor,
                fontWeight: activeTab === tab ? 'bold' : 'normal',
                transition: 'color 0.2s',
              }}
            >
              {tab}
            </Typography>
          ))}
        </Box>

        <Box sx={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
          {/* Sidebar List Area - Only show for Portfolio and Traders tabs */}
          {activeTab !== 'analytics' && (
            <Box sx={{ width: 350, borderRight: '1px solid #333', display: 'flex', flexDirection: 'column' }}>
              <Box sx={{ p: 2, borderBottom: '1px solid #333', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography variant="overline">
                  Sort by {activeTab === 'portfolio' ? 'Price' : 'PnL'}
                </Typography>
                <Button
                  size="small"
                  variant="outlined"
                  sx={{ color: activeColor, borderColor: '#333' }}
                  onClick={() => {
                    if (activeTab === 'portfolio') setCoinSort(prev => prev === 'desc' ? 'asc' : 'desc');
                    else setTraderSort(prev => prev === 'desc' ? 'asc' : 'desc');
                  }}
                >
                  {(activeTab === 'portfolio' ? coinSort : traderSort) === 'desc' ? 'Highest' : 'Lowest'}
                </Button>
              </Box>
              
              <List sx={{ overflowY: 'auto', flex: 1 }}>
                {activeTab === 'portfolio' ? (
                  sortedCoins.map((coin) => (
                    <CoinListItem
                      key={coin.id}
                      {...coin}
                      isSelected={selectedCoinId === coin.id}
                      onSelect={() => setSelectedCoinId(coin.id)}
                    />
                  ))
                ) : (
                  sortedTraders.map((trader) => (
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
          )}

          {/* Main Detail Area */}
          <Box sx={{ flex: 1, overflowY: 'auto' }}>
            {activeTab === 'portfolio' && <CoinDetailView coin={selectedCoin} />}
            {activeTab === 'traders' && <TraderDetailView trader={selectedTrader} />}
            {activeTab === 'analytics' && <AnalyticsView />}
          </Box>
        </Box>
      </Box>
    </ThemeProvider>
  );
}