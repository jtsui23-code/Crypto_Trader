import { memo } from 'react';
import { ListItem, ListItemButton, ListItemAvatar, Avatar, ListItemText } from '@mui/material';

interface CoinListItemProps {
  id: string;
  symbol: string;
  entry_price: number;
  isSelected: boolean;
  onSelect: (id: string) => void;
}

export const CoinListItem = memo(({ id, symbol, entry_price, isSelected, onSelect }: CoinListItemProps) => (
  <ListItem disablePadding sx={{ borderBottom: 1 }}>
    <ListItemButton 
      onClick={() => onSelect(id)} 
      selected={isSelected}
      sx={{ 
        py: 2,
        '&.Mui-selected': { backgroundColor: 'rgba(255, 255, 255, 0.15)' },
        '&.Mui-selected:hover': { backgroundColor: 'rgba(255, 255, 255, 0.2)' },
      }}
    >
      <ListItemAvatar>
        <Avatar sx={{ border: 1, borderColor: 'divider', bgcolor: 'background.paper', color: 'primary.main', fontSize: '0.8rem' }}>
          {symbol.substring(0, 3).toUpperCase()}
        </Avatar>
      </ListItemAvatar>
      <ListItemText primary={symbol.length > 15 ? `${symbol.substring(0, 6)}...` : symbol} secondary={`Entry: $${entry_price.toFixed(6)}`} />
    </ListItemButton>
  </ListItem>
));