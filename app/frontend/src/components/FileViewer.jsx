import React from 'react';

export default function FileViewer({ content }) {
  const [needle, setNeedle] = React.useState('');
  const [idx, setIdx] = React.useState(0);
  const containerRef = React.useRef(null);

  const escapeHtml = (s) =>
    s.replace(/&/g, '&amp;')
     .replace(/</g, '&lt;')
     .replace(/>/g, '&gt;');

  const escapeRegex = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  // Build highlighted HTML WITHOUT setting state during render
  const { html, count } = React.useMemo(() => {
    const safe = escapeHtml(content || '');
    const q = (needle || '').trim();
    if (!q) {
      return { html: `<code>${safe}</code>`, count: 0 };
    }
    const pattern = new RegExp(escapeRegex(q), 'gi'); // case-insensitive
    let n = 0;
    const replaced = safe.replace(pattern, (m) => {
      // mark all hits; the "current" one is chosen by idx (passed in deps)
      const currentClass = (n === idx) ? ' current' : '';
      const out = `<mark class="hit${currentClass}" data-hit="${n}">${escapeHtml(m)}</mark>`;
      n += 1;
      return out;
    });
    return { html: `<code>${replaced}</code>`, count: n };
  }, [content, needle, idx]);

  // Clamp idx when the search term changes or match count shrinks
  React.useEffect(() => {
    if (idx >= count && count > 0) setIdx(count - 1);
    if (count === 0 && idx !== 0) setIdx(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needle, content, count]);

  // Scroll current hit into view after render
  React.useEffect(() => {
    if (!needle || !count) return;
    const el = containerRef.current?.querySelector('mark.hit.current');
    if (el) el.scrollIntoView({ block: 'center', inline: 'nearest' });
  }, [needle, idx, count]);

  const goNext = () => { if (count) setIdx((idx + 1) % count); };
  const goPrev = () => { if (count) setIdx((idx - 1 + count) % count); };

  const onKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (e.shiftKey) goPrev(); else goNext();
    }
  };

  // Reset current index to first match whenever the needle changes
  React.useEffect(() => { setIdx(0); }, [needle, content]);

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:8, minHeight:0 }}>
      <div style={{ display:'flex', gap:8, alignItems:'center' }}>
        <input
          value={needle}
          onChange={e=>setNeedle(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Find in file (case-insensitive). Enter=Next, Shift+Enter=Prev"
          style={{ flex:1 }}
        />
        <div style={{ fontSize:12, color:'#666', width:80, textAlign:'right' }}>
          {count ? `${Math.min(idx + 1, count)}/${count}` : '0/0'}
        </div>
        <button onClick={goPrev} disabled={!count}>◀</button>
        <button onClick={goNext} disabled={!count}>▶</button>
      </div>

      <pre
        ref={containerRef}
        style={{
          flex:1,
          margin:0,
          padding:12,
          background:'#0f172a',
          color:'#e2e8f0',
          borderRadius:6,
          overflow:'auto',
          lineHeight:1.4,
          fontFamily:'ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace',
          fontSize:13
        }}
        dangerouslySetInnerHTML={{ __html: html }}
      />
      <style>{`
        mark.hit { background: #fff3a3; color: inherit; padding: 0 1px; }
        mark.hit.current { background: #ffd24d; outline: 1px solid #caa300; }
      `}</style>
    </div>
  );
}
