import { useState, useEffect } from 'react';
import { Box, List, Typography, CssBaseline } from '@mui/material';

import { CoinListItem } from './components/CoinListItem';
import { CoinDetailView } from './components/CoinDetailView';

import { TraderListItem } from './components/TraderListItem';
import { TraderDetailView } from './components/TraderDetailView';

interface Coin {
  id: string;          // token_out_mint
  symbol: string;      // token_symbol
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
}

const backgroundColor = '#0a0a0a';

const activeColor = '#208dd1';
const inactiveColor = '#FFFFFF';

const activeWeight = 'bold';
const inactiveWeight = 'normal';

const tabTransition = 'color 0.2s';


export default function App() {
  document.title = "Crypto Trader Dashboard";
  document.body.style.backgroundColor = backgroundColor;

  // Set our state for the active tab, selected coin, and selected trader
  const [activeTab, setActiveTab] = useState<'portfolio' | 'traders'>('portfolio');
  const [selectedCoinId, setSelectedCoinId] = useState<string>('1');
  const [selectedTraderId, setSelectedTraderId] = useState<string | null>(null);

  // State for coins and traders
  const [coins, setCoins] = useState<Coin[]>([]);
  const [traders, setTraders] = useState<Trader[]>([]);

  useEffect(() => {
    // Fetch Traders
    fetch('http://localhost:8000/api/traders')
      .then((res) => res.json())
      .then((data) => {
        const traderArray = Array.isArray(data) ? data : (data.wallets || []);
        setTraders(traderArray);
      })
      .catch((err) => console.error("Error loading traders:", err));

    // Fetch Portfolio Coins
    fetch('http://localhost:8000/api/portfolio/positions')
      .then((res) => res.json())
      .then((data) => {
        setCoins(data);
        // Set default selection to the first coin if available
        if (data.length > 0) setSelectedCoinId(data[0].id);
      })
      .catch((err) => console.error("Error loading portfolio:", err));
  }, []);

  // Find the selected coin and trader based on the selected IDs
  const selectedCoin = coins.find((c) => c.id === selectedCoinId);
  const selectedTrader = traders.find((t) => t.id === selectedTraderId);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh', bgcolor: backgroundColor, color: 'white' }}>
      <CssBaseline />

      {/* Tab Navigation */}
      <Box sx={{ p: 2, borderBottom: '1px solid #333', display: 'flex', gap: 4 }}>
        <Typography 
          onClick={() => setActiveTab('portfolio')}
          sx={{ 
            cursor: 'pointer', 
            color: activeTab === 'portfolio' ? activeColor : inactiveColor,
            fontWeight: activeTab === 'portfolio' ? activeWeight : inactiveWeight,
            transition: tabTransition
          }}
        >
          Portfolio
        </Typography>
        <Typography 
          onClick={() => setActiveTab('traders')}
          sx={{ 
            cursor: 'pointer', 
            color: activeTab === 'traders' ? activeColor : inactiveColor,
            fontWeight: activeTab === 'traders' ? activeWeight : inactiveWeight,
            transition: tabTransition
          }}
        >
          Top Traders
        </Typography>
      </Box>

      {/* Main Content Area */}
      <Box sx={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <Box sx={{ width: 350, borderRight: '1px solid #333', overflowY: 'auto' }}>
          {/* List of coins or traders depending on the active tab */}
          <List>
            {activeTab === 'portfolio' ? (
              coins.length > 0 ? (
                coins.map((coin) => (
                  <CoinListItem 
                    key={coin.id}
                    {...coin}
                    isSelected={selectedCoinId === coin.id}
                    onSelect={() => setSelectedCoinId(coin.id)}
                  />
                ))
              ) : (
                <Typography sx={{ p: 2, color: 'gray' }}>No positions found.</Typography>
              )) : (
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

        {/* Detail View */}
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