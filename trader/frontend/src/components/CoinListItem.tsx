import { ListItem, ListItemButton, ListItemAvatar, Avatar, ListItemText } from '@mui/material';

interface CoinListItemProps {
  name: string;
  price: string;
  symbol: string;
  isSelected: boolean;
  onSelect: () => void;
}

export const CoinListItem = ({ name, price, symbol, isSelected, onSelect }: CoinListItemProps) => (
  // We use disablePadding because the padding now lives inside the ListItemButton
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
        <Avatar sx={{ border: '1px solid #fff', bgcolor: 'transparent' }}>
          {symbol[0]}
        </Avatar>
      </ListItemAvatar>
      <ListItemText primary={name} secondary={price} />
    </ListItemButton>
  </ListItem>
);