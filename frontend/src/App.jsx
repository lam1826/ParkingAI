import React from 'react';
import { BrowserRouter } from 'react-router-dom';
import AppRouter from './routes/AppRouter';

function App() {
  return (
    // Bọc AppRouter bên trong BrowserRouter để các Route hoạt động được
    <BrowserRouter>
      <AppRouter />
    </BrowserRouter>
  );
}

export default App;