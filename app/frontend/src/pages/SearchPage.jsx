import React, { useEffect, useRef, useState } from 'react';
import { getStatus, startIndexing, searchApi, fetchDoc } from '../api';
import SearchBar from '../components/SearchBar';
import ResultsList from '../components/ResultsList';
import FileViewer from '../components/FileViewer';

export default function SearchPage() {
  const [q, setQ] = useState('');
  const [limit, setLimit] = useState(100);
  const [total, setTotal] = useState(0);
  const [hits, setHits] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');

  const [selectedPath, setSelectedPath] = useState(null);
  const [doc, setDoc] = useState(null);
  const [docLoading, setDocLoading] = useState(false);
  const [docError, setDocError] = useState('');

  const pollRef = useRef(null);
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  async function runSearch() {
    setError(''); setInfo('');
    const query = (q || '').trim();
    if (!query) { setError('Enter a query'); return; }

    const status = await getStatus().catch(() => ({ indexing: false }));
    if (status.indexing) {
      setInfo('Indexing in progress — please try again in a moment.');
      return;
    }

    setLoading(true);
    try {
      const res = await searchApi({ q: query, limit, offset: 0 });
      if (res.status === 423) { setInfo('Indexing in progress — please try again in a moment.'); setLoading(false); return; }
      const data = await res.json();
      if (data.detail) throw new Error(data.detail);
      setHits(data.hits || []);
      setTotal(data.total || 0);
      setSelectedPath(null); setDoc(null); setDocError(''); setDocLoading(false);
    } catch (e) {
      setError(e.message || 'Search error');
      setHits([]); setTotal(0);
    } finally {
      setLoading(false);
    }
  }

  function startIndexPolling() {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      const status = await getStatus().catch(() => ({ indexing: false }));
      if (!status.indexing) {
        clearInterval(pollRef.current);
        pollRef.current = null;
        setInfo('');
        if (status.last_result && typeof status.last_result.indexed !== 'undefined') {
          setInfo(`Indexing completed — indexed: ${status.last_result.indexed}`);
          setTimeout(() => setInfo(''), 2500);
        }
      } else {
        setInfo('Indexing in progress — please wait…');
      }
    }, 1500);
  }

  async function onReindexClick() {
    setError('');
    const status = await getStatus().catch(() => ({ indexing: false }));
    if (status.indexing) { setInfo('Indexing already in progress…'); startIndexPolling(); return; }

    try {
      const res = await startIndexing();
      if (res.status === 409) setInfo('Indexing already in progress…');
      else if (res.ok) setInfo('Indexing started. Please wait…');
      else setError(`Failed to start indexing: ${await res.text()}`);
      startIndexPolling();
    } catch (e) {
      setError(`Failed to start indexing: ${e.message}`);
    }
  }

  async function onSelectHit(hit) {
    setSelectedPath(hit.path);
    setDoc(null);
    setDocError('');
    setDocLoading(true);
    try {
      const res = await fetchDoc(hit.path);
      if (res.status === 423) { setDocError('Indexing in progress'); setDocLoading(false); return; }
      if (!res.ok) throw new Error(await res.text());
      const full = await res.json();
      setDoc(full);
    } catch (e) {
      setDocError(e.message || 'Failed to fetch document');
    } finally {
      setDocLoading(false);
    }
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ flex: '0 0 auto' }}>
        <SearchBar
          q={q} onChangeQ={setQ}
          onSubmit={runSearch}
          onReindex={onReindexClick}
        />
        {info && <div style={{ color:'#555', marginBottom:8 }}>{info}</div>}
        {error && <div style={{ color:'red', marginBottom:8 }}>{error}</div>}
        {loading && <div style={{ marginBottom:8 }}>Loading…</div>}
      </div>

      {/* Split view fills remaining space */}
        <div
          style={{
            flex: 1,
            display: 'grid',
            gridTemplateColumns: 'minmax(280px, 40%) 1fr',
            gap: 12,
            borderTop: '1px solid #eee',
            padding: 12,
            minHeight: 0,
            overflow: 'hidden'
          }}
        >
        <ResultsList
          hits={hits}
          total={total}
          onSelect={onSelectHit}
          selectedPath={selectedPath}
        />

        <div style={{ overflow: 'hidden', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          {!selectedPath && <div style={{ color:'#666' }}>Select a result to view the file.</div>}
          {selectedPath && (
            <>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
                <div style={{ fontWeight:600 }}>{doc?.filename || '...'}</div>
                <small style={{ color:'#666', marginLeft:12, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>
                  {selectedPath}
                </small>
              </div>
              {docLoading && <div>Loading file…</div>}
              {docError && <div style={{ color:'red' }}>{docError}</div>}
              {doc && <FileViewer content={doc.content} />}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
