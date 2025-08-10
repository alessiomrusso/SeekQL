import React from 'react';
import SearchPage from './pages/SearchPage';
import './index.css';

export default function App() {
  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <header style={{ padding: '8px 20px', flex: '0 0 auto' }}>
        <h1 style={{ margin: 0 }}>SeekQL (PoC)</h1>
      </header>
      <div style={{ flex: 1, minHeight: 0 }}>
        <SearchPage />
      </div>
    </div>
  );
}
