import React, { useEffect, useMemo, useState } from 'react';

function normalizePaths(config) {
  const list = Array.isArray(config?.sql_source_paths) ? config.sql_source_paths : [];
  // backend returns objects {input, resolved,...}; accept plain strings too
  return list.map((p) => {
    if (p && typeof p === 'object') return p.resolved || p.input || '';
    return String(p || '');
  });
}

export default function ConfigPanel({ config, onClose, onRefresh, onSave }) {
  const incoming = useMemo(() => normalizePaths(config), [config]);
  const [paths, setPaths] = useState(incoming);
  const [newPath, setNewPath] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // Robustly sync local state with incoming config after refresh/open
  useEffect(() => {
    const incomingStr = JSON.stringify(incoming);
    const localStr = JSON.stringify(paths);
    if (incomingStr !== localStr) {
      setPaths(incoming);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incoming]); // compare contents, not just reference

  const removeAt = (i) => setPaths((prev) => prev.filter((_, idx) => idx !== i));

  const addPath = () => {
    const p = newPath.trim();
    if (!p) return;
    setPaths((prev) => [...prev, p]);
    setNewPath('');
  };

  const doSave = async () => {
    setError('');
    setSaving(true);
    try {
      await onSave(paths);
    } catch (e) {
      setError(e.message || 'Failed to save config');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.4)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
    >
      <div
        style={{
          width: 800,
          maxWidth: '95vw',
          maxHeight: '85vh',
          overflow: 'auto',
          background: '#fff',
          borderRadius: 8,
          boxShadow: '0 10px 30px rgba(0,0,0,0.2)',
          padding: 16,
        }}
      >
        <div
          style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}
        >
          <h2 style={{ margin: 0 }}>SeekQL Configuration</h2>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={onRefresh} disabled={saving}>
              Refresh
            </button>
            <button onClick={onClose} disabled={saving}>
              Close
            </button>
          </div>
        </div>

        <div style={{ fontSize: 13, color: '#444', marginBottom: 12 }}>
          <div>
            <b>Config file:</b> {config?.config_file}{' '}
            {config?.config_present ? '' : '(not found — will be created on Save)'}
          </div>
          <div>
            <b>Indexing now:</b> {config?.indexing ? 'yes' : 'no'}
          </div>
          <div>
            <b>Current docs in index:</b> {config?.doc_count ?? 0}
          </div>
          {config?.preserve_comments === false && (
            <div style={{ color: '#a00', marginTop: 6 }}>
              Saving might remove YAML comments. Install <code>ruamel.yaml</code> to preserve them.
            </div>
          )}
        </div>

        <div style={{ marginBottom: 12 }}>
          <b>Source paths</b>
          <ul style={{ listStyle: 'none', padding: 0, marginTop: 8 }}>
            {paths.length === 0 && <li style={{ color: '#a00' }}>No folders configured.</li>}
            {paths.map((p, i) => (
              <li
                key={`${i}-${p}`}
                style={{
                  display: 'flex',
                  gap: 8,
                  alignItems: 'center',
                  border: '1px solid #eee',
                  borderRadius: 6,
                  padding: '8px',
                  marginBottom: 8,
                }}
              >
                <input
                  value={p}
                  onChange={(e) => {
                    const v = e.target.value;
                    setPaths((prev) => prev.map((x, idx) => (idx === i ? v : x)));
                  }}
                  style={{ flex: 1 }}
                  placeholder="C:\path\to\sql or ./relative/folder"
                />
                <button onClick={() => removeAt(i)} title="Remove">
                  Remove
                </button>
              </li>
            ))}
          </ul>

          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <input
              value={newPath}
              onChange={(e) => setNewPath(e.target.value)}
              placeholder="Add new path…"
              style={{ flex: 1 }}
            />
            <button onClick={addPath}>Add</button>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          {error && <div style={{ color: '#c00', marginRight: 'auto' }}>{error}</div>}
          <button onClick={doSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>

        <div style={{ marginTop: 8, fontSize: 12, color: '#666' }}>
          Your paths are stored in <code>seekql.config.yml</code>. It’s gitignored; commit{' '}
          <code>seekql.config.yml.example</code> instead.
        </div>
      </div>
    </div>
  );
}
