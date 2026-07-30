import React from 'react';
import { Card, CardContent, Typography, Skeleton, Box } from '@mui/material';

const SummaryCard = ({ title, value, loading, unit = "" }) => {
  return (
    <Card sx={{ height: '100%', boxShadow: 3 }}>
      <CardContent>
        {/* Đưa textTransform vào trong object sx để tránh cảnh báo DOM */}
        <Typography color="textSecondary" gutterBottom variant="subtitle2" sx={{ textTransform: 'uppercase' }}>
          {title}
        </Typography>
        <Box sx={{ mt: 2 }}>
          {loading ? (
            <Skeleton variant="text" width="80%" height={40} />
          ) : (
            <Typography variant="h4" component="div" fontWeight="bold" color="primary">
              {value !== undefined && value !== null ? `${value} ${unit}` : "0"}
            </Typography>
          )}
        </Box>
      </CardContent>
    </Card>
  ); 
};

export default SummaryCard;