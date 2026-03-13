// src/components/TraderListItem.tsx
import { ListItem, ListItemButton, ListItemText, Typography } from '@mui/material';

interface TraderProps {
  name: string;
  record: string;
  isSelected: boolean;
  onSelect: () => void;
}

export const TraderListItem = ({ name, record, isSelected, onSelect }: TraderProps) => (
  <ListItem disablePadding sx={{ borderBottom: '1px solid #222' }}>
    <ListItemButton selected={isSelected} onClick={onSelect} sx={{ py: 2 }}>
      <ListItemText 
        primary={name} 
        secondary={<Typography variant="body2" color="success.main">{record}</Typography>} 
      />
    </ListItemButton>
  </ListItem>
);