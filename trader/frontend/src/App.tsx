import { useState, useEffect, useMemo, useRef } from 'react';
import { Box, List, Typography, CssBaseline, Button } from '@mui/material';
import { ThemeProvider, createTheme } from '@mui/material/styles';

import { CoinListItem } from './components/CoinListItem';
import { CoinDetailView } from './components/CoinDetailView';
import { TraderListItem } from './components/TraderListItem';
import { TraderDetailView } from './components/TraderDetailView';
import { AnalyticsView } from './components/AnalyticsView';
import { LiveFeedView } from './components/LiveFeedView';
import { SettingsView } from './components/SettingsView';

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

const activeColor = '#208dd1';
const inactiveColor = '#115e8f';

const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    background: {
      default: '#000000',
      paper: '#00000090',
    },
    text: {
      primary: '#e6e0f0',
      secondary: '#acaaae',
    },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
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
  const [activeTab, setActiveTab] = useState<'feed' | 'portfolio' | 'traders' | 'analytics' | 'settings'>('feed');
  const [selectedCoinId, setSelectedCoinId] = useState<string | null>(null);
  const [selectedTraderId, setSelectedTraderId] = useState<string | null>(null);

  // Data states
  const [coins, setCoins] = useState<Coin[]>([]);
  const [traders, setTraders] = useState<Trader[]>([]);

  const latestCoins = useRef<Coin[] | null>(null);
  const latestTraders = useRef<Trader[] | null>(null);

  // Sorting statess
  const [traderSort, setTraderSort] = useState<'desc' | 'asc'>('desc');
  const [coinSort, setCoinSort] = useState<'desc' | 'asc'>('desc');

  
  // Pinned Traders State
  const [pinnedTraders, setPinnedTraders] = useState<string[]>(() => {
    const saved = localStorage.getItem('pinnedTraders');
    return saved ? JSON.parse(saved) : [];
  });


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

  // Save pinned traders to local storage whenever they change
  const fetchPinnedTraders = () => {
    localStorage.setItem('pinnedTraders', JSON.stringify(pinnedTraders));
  };

  useEffect(() => {
    const interval = setInterval(() => {
      if (latestCoins.current) {
        setCoins(latestCoins.current);
        latestCoins.current = null;
      }
      if (latestTraders.current) {
        setTraders([...latestTraders.current]);
        latestTraders.current = null;
      }
    }, 500);
    return () => clearInterval(interval);
  }, []);

  // Initial data fetch and setup auto-refresh
  useEffect(() => {
    fetchCoins();
    fetchTraders();
    fetchPinnedTraders();

    const wsPositions = new WebSocket('ws://localhost:8000/ws/positions');
    wsPositions.onmessage = (event) => {
      const data = JSON.parse(event.data);
      latestCoins.current = Array.isArray(data) ? data : (data.positions || []);
    };

    const wsTraders = new WebSocket('ws://localhost:8000/ws/traders');
    wsTraders.onmessage = (event) => {
      const data = JSON.parse(event.data);
      latestTraders.current = Array.isArray(data) ? data : (data.wallets || []);
    };

    return () => {
      wsPositions.close();
      wsTraders.close();
    };
  }, [pinnedTraders]);

  // Sorting logic (Pins first, then by PnL)
  const sortedTraders = useMemo(() => {
    return [...traders].sort((a, b) => {
      const aPinned = pinnedTraders.includes(a.id);
      const bPinned = pinnedTraders.includes(b.id);
      if (aPinned && !bPinned) return -1;
      if (!aPinned && bPinned) return 1;

      const pnlA = a.total_pnl || 0;
      const pnlB = b.total_pnl || 0;
      return traderSort === 'desc' ? pnlB - pnlA : pnlA - pnlB;
    });
  }, [traders, traderSort, pinnedTraders]);

  const sortedCoins = useMemo(() => {
    return [...coins].sort((a, b) => {
      const priceA = a.entry_price || 0;
      const priceB = b.entry_price || 0;
      return coinSort === 'desc' ? priceB - priceA : priceA - priceB;
    });
  }, [coins, coinSort]);
 
  // Find selected items
  const selectedCoin = coins.find((c) => c.id === selectedCoinId);
  const selectedTrader = traders.find((t) => t.id === selectedTraderId);

  // Render
  return (
    <ThemeProvider theme={darkTheme}>
      <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
        <CssBaseline />

        {/* Navigation Tabs */}
        <Box 
          sx={{ 
            p: 2, 
            borderBottom: '1px solid #333', 
            display: 'flex', 
            gap: 6,
            backgroundColor: '#00000080',
          }}>
          {['feed', 'portfolio', 'traders', 'analytics', 'settings'].map((tab) => (
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

        {/* Main Content Area */}
        <Box sx={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
          {/* Sidebar List Area - Only show for Portfolio and Traders tabs */}
          {activeTab !== 'analytics' && activeTab !== 'feed' && (
            <Box sx={{ width: 350, borderRight: '1px solid #333', display: 'flex', flexDirection: 'column' }}>
              <Box sx={{ p: 2, backgroundColor: '#00000050', borderBottom: '1px solid #333', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
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
              
              <List sx={{ overflowY: 'auto', backgroundColor: '#00000050', flex: 1 }}>
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
                      isPinned={pinnedTraders.includes(trader.id)}
                      onSelect={() => setSelectedTraderId(trader.id)}
                      onTogglePin={(e) => {
                        e.stopPropagation(); // Prevents row selection when clicking the star
                        setPinnedTraders(prev => 
                          prev.includes(trader.id) 
                            ? prev.filter(id => id !== trader.id) 
                            : [...prev, trader.id]
                        );
                      }}
                    />
                  ))
                )}
              </List>
            </Box>
          )}

          {/* Main Detail Area */}
          <Box sx={{ flex: 1, backgroundColor: '#00000009', overflowY: 'auto' }}>
            <Box sx={{ display: activeTab === 'feed' ? 'block' : 'none'}}>
              <LiveFeedView />
            </Box>
            
            <Box sx={{ display: activeTab === 'portfolio' ? 'block' : 'none' }}>
              <CoinDetailView coin={selectedCoin} />
            </Box>
            
            <Box sx={{ display: activeTab === 'traders' ? 'block' : 'none'}}>
              <TraderDetailView trader={selectedTrader} />
            </Box>
            
            <Box sx={{ display: activeTab === 'analytics' ? 'block' : 'none' }}>
              <AnalyticsView />
            </Box>

            <Box sx={{ display: activeTab === 'settings' ? 'block' : 'none' }}>
              <SettingsView />
            </Box>
          </Box>  
        </Box>
      </Box>
    </ThemeProvider>
  );
}