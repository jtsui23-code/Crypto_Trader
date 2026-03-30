import { ListItem, ListItemButton, ListItemAvatar, Avatar, ListItemText } from '@mui/material';

interface CoinListItemProps {
  symbol: string;
  entry_price: number;
  isSelected: boolean;
  onSelect: () => void;
}

export const CoinListItem = ({ symbol, entry_price, isSelected, onSelect }: CoinListItemProps) => (
  <ListItem disablePadding sx={{ borderBottom: '1px solid #222' }}>
    <ListItemButton 
      onClick={onSelect} 
      selected={isSelected}
      sx={{ 
        py: 2,
        '&.Mui-selected': { backgroundColor: 'rgba(255, 255, 255, 0.15)' },
        '&.Mui-selected:hover': { backgroundColor: 'rgba(255, 255, 255, 0.2)' },
      }}
    >
      <ListItemAvatar>
        <Avatar sx={{ border: '1px solid #fff', bgcolor: 'transparent', fontSize: '0.8rem' }}>
          {symbol.substring(0, 3)}
        </Avatar>
      </ListItemAvatar>
      <ListItemText 
        primary={symbol.length > 15 ? `${symbol.substring(0, 6)}...` : symbol} 
        secondary={`Entry: $${entry_price.toFixed(6)}`} 
      />
    </ListItemButton>
  </ListItem>
);