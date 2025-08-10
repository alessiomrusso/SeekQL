import React from 'react';

export default function ResultsList({ hits, total, onSelect, selectedPath }) {
  return (
    <div style={{ borderRight:'1px solid #eee', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
        <div>Total: {total}</div>
      </div>
      <div style={{ overflow:'auto', flex: 1 }}>
        <ul style={{ listStyle:'none', padding:0, margin:0 }}>
          {hits.map(h => {
            const active = h.path === selectedPath;
            return (
              <li
                key={h.path}
                onClick={()=>onSelect && onSelect(h)}
                style={{
                  padding:'10px 8px',
                  cursor:'pointer',
                  background: active ? '#eef5ff' : 'transparent',
                  borderBottom:'1px solid #f0f0f0'
                }}
                title={h.path}
              >
                <div style={{ fontWeight:600, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>
                  {h.filename}
                </div>
                <div style={{ color:'#666', fontSize:12, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>
                  {h.path}
                </div>
                <div
                  style={{ fontSize:12, color:'#333', marginTop:4 }}
                  dangerouslySetInnerHTML={{ __html: h.snippet || '' }}
                />
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
