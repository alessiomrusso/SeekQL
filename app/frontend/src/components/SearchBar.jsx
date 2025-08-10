import React from 'react';

export default function SearchBar({ q, onChangeQ, onSubmit, onReindex, onOpenConfig }) {
  return (
    <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
      <input
        type="text"
        value={q}
        onChange={(e) => onChangeQ(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && onSubmit()}
        placeholder="Enter search query..."
        style={{ flex: 1 }}
      />
      <button onClick={onSubmit}>Search</button>
      <button onClick={onReindex}>Reindex</button>
      <button onClick={onOpenConfig}>Config</button>
    </div>
  );
}
