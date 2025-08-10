export async function getStatus() {
  const res = await fetch('/status');
  return res.json();
}

export async function startIndexing() {
  const res = await fetch('/index', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({})
  });
  return res;
}

export async function searchApi({ q, offset }) {
  const params = new URLSearchParams({
    q, highlight: 'true', offset: String(offset)
  });
  const res = await fetch(`/search?${params.toString()}`);
  return res;
}

export async function fetchDoc(path) {
  const res = await fetch(`/doc?path=${encodeURIComponent(path)}`);
  return res;
}

async function requestJson(url, options) {
  const res = await fetch(url, options);
  const text = await res.text();
  let data = null;
  if (text) {
    try { data = JSON.parse(text); }
    catch { throw new Error(`HTTP ${res.status} — Non-JSON response`); }
  }
  if (!res.ok) {
    const msg = data?.detail || data?.message || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data ?? {};
}

export async function getConfigApi() {
  return requestJson('/config');
}

export async function saveConfigApi(paths) {
  const res = await fetch('/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sql_source_paths: paths })
  });
  const text = await res.text();
  if (!res.ok) throw new Error(text || `HTTP ${res.status}`);
  return JSON.parse(text || '{}');
}