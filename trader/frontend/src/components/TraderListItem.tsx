import { memo } from 'react';
import { ListItem, ListItemButton, ListItemAvatar, Avatar, ListItemText, IconButton } from '@mui/material';

interface TraderProps {
  id: string;
  name: string;
  record: string;
  isSelected: boolean;
  isPinned: boolean;
  onSelect: (id: string) => void;
  onTogglePin: (id: string, e: React.MouseEvent) => void;
}

const StarIcon = () => (
  <svg viewBox="0 0 24 24" fill="var(--accent-color)" width="15px" height="15px">
    <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/>
  </svg>
);

const StarBorderIcon = () => (
  <svg viewBox="0 0 24 24" fill="var(--accent-color)" width="15px" height="15px">
    <path d="M22 9.24l-7.19-.62L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21 12 17.27 18.18 21l-1.63-7.03L22 9.24zM12 15.4l-3.76 2.27 1-4.28-3.32-2.88 4.38-.38L12 6.1l1.71 4.04 4.38.38-3.32 2.88 1 4.28L12 15.4z"/>
  </svg>
);

export const TraderListItem = memo(({ id, name, record, isSelected, isPinned, onSelect, onTogglePin }: TraderProps) => (
  <ListItem 
    disablePadding 
    sx={{ 
      borderBottom: 1,
      '& .MuiListItemSecondaryAction-root': { top: '0px', right: '6px', transform: 'none' }
    }}
    secondaryAction={
      <IconButton edge="end" onClick={(e) => onTogglePin(id, e)}>
        {isPinned ? <StarIcon /> : <StarBorderIcon />}
      </IconButton>
    }
  >
    <ListItemButton 
      onClick={() => onSelect(id)} 
      selected={isSelected}
      sx={{ 
        py: 2, pr: 7, 
        '&.Mui-selected': { bgcolor: 'action.selected' },
        '&.Mui-selected:hover': { bgcolor: 'action.hover' }
      }}
    >
      <ListItemAvatar>
        <Avatar sx={{ border: 1, borderColor: 'divider', bgcolor: 'background.paper', color: 'primary.main', fontSize: '0.8rem' }}>
          {name.substring(0, 3).toUpperCase()}
        </Avatar>
      </ListItemAvatar>
      <ListItemText primary={name} secondary={record} />
    </ListItemButton>
  </ListItem>
));