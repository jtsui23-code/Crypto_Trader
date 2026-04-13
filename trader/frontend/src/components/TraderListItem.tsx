import { ListItem, ListItemButton, ListItemAvatar, Avatar, ListItemText } from '@mui/material';

interface TraderProps {
  name: string;
  record: string;
  isSelected: boolean;
  onSelect: () => void;
}

// TraderListItem component for displaying individual traders in the sidebar list
export const TraderListItem = ({ name, record, isSelected, onSelect }: TraderProps) => (
  <ListItem disablePadding sx={{ borderBottom: '1px solid #333' }}>
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
        <Avatar sx={{ 
          border: '1px solid #333', 
          bgcolor: 'background.paper', 
          color: '#fff',
          fontSize: '0.8rem' 
        }}>
          {name.substring(0, 3).toUpperCase()}
        </Avatar>
      </ListItemAvatar>
      <ListItemText 
        primary={name} 
        secondary={record} 
      />
    </ListItemButton>
  </ListItem>
);