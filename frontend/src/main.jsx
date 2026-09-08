import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { ThemeProvider, CssBaseline } from '@mui/material';

import App from './App.jsx';
import theme from './theme'; // Đường dẫn tới file theme của bạn
import ErrorBoundary from './components/common/ErrorBoundary.jsx';
import { recoverChunkError } from './utils/chunkRecovery.js';

window.addEventListener('vite:preloadError', (event) => {
  if (recoverChunkError(event.payload || new Error('vite:preloadError'))) {
    event.preventDefault();
  }
});

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      {/* Lưới an toàn cuối cùng: một lỗi render không được làm trắng toàn bộ SPA */}
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </ThemeProvider>
  </StrictMode>
);
