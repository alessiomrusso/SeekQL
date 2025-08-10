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

export async function searchApi({ q, limit, offset }) {
  const params = new URLSearchParams({
    q, highlight: 'true', limit: String(limit), offset: String(offset)
  });
  const res = await fetch(`/search?${params.toString()}`);
  return res;
}

export async function fetchDoc(path) {
  const res = await fetch(`/doc?path=${encodeURIComponent(path)}`);
  return res;
}
