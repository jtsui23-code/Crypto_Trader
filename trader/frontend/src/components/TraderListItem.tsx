import { memo } from 'react';
import { ListItem, ListItemButton, ListItemAvatar, Avatar, ListItemText, IconButton } from '@mui/material';

interface TraderProps {
  name: string;
  record: string;
  isSelected: boolean;
  isPinned: boolean;
  onSelect: () => void;
  onTogglePin: (e: React.MouseEvent) => void;
}

const StarIcon = () => (
  <svg viewBox="0 0 24 24" fill="#ffd700" width="20px" height="20px">
    <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/>
  </svg>
);

const StarBorderIcon = () => (
  <svg viewBox="0 0 24 24" fill="#acaaae" width="20px" height="20px">
    <path d="M22 9.24l-7.19-.62L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21 12 17.27 18.18 21l-1.63-7.03L22 9.24zM12 15.4l-3.76 2.27 1-4.28-3.32-2.88 4.38-.38L12 6.1l1.71 4.04 4.38.38-3.32 2.88 1 4.28L12 15.4z"/>
  </svg>
);

export const TraderListItem = memo(({ name, record, isSelected, isPinned, onSelect, onTogglePin }: TraderProps) => (
  <ListItem 
    disablePadding 
    sx={{ borderBottom: '1px solid #333' }}
    secondaryAction={
      <IconButton edge="end" onClick={onTogglePin} sx={{ mr: 1 }}>
        {isPinned ? <StarIcon /> : <StarBorderIcon />}
      </IconButton>
    }
  >
    <ListItemButton 
      onClick={onSelect} 
      selected={isSelected}
      sx={{ 
        py: 2,
        pr: 7, 
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
));