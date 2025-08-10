# app/backend/main.py
import os
import re
import threading
import time
import traceback
import pathlib
from typing import Optional, List

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from opensearchpy.exceptions import NotFoundError

from pydantic import BaseModel, Field

from .schemas import IndexRequest
from .indexer import reindex, client, ensure_index, reset_index, INDEX_NAME, inspect_config, save_config

app = FastAPI(title="SeekQL")

FRONT_DIR = os.getenv("FRONT_DIST", str(pathlib.Path(__file__).parents[1] / "frontend" / "dist"))
if os.path.exists(FRONT_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONT_DIR, "assets")), name="assets")

    @app.get("/")
    def root() :
        return FileResponse(os.path.join(FRONT_DIR, "index.html"))

# CORS for the Vite dev server (adjust if needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("CORS_ORIGINS", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# In-memory indexing state
# ---------------------------
_index_state = {
    "indexing": False,        # bool
    "started_at": None,       # float | None (epoch seconds)
    "finished_at": None,      # float | None
    "last_result": None,      # dict | None  (e.g., {"indexed": n, "considered": m, ...})
    "last_error": None,       # str | None   (stacktrace or message)
    "phase": "idle",          # "idle" | "reset" | "collect" | "bulk" | "done" | "error"
}
_state_lock = threading.Lock()


def _set_state(**kwargs) -> None:
    with _state_lock:
        _index_state.update(kwargs)


def _run_reindex(roots: Optional[List[str]]):
    _set_state(indexing=True, started_at=time.time(), finished_at=None,
               last_result=None, last_error=None, phase="collect")
    try:
        # reindex will call our phase callback ("collect" -> "bulk" -> "done")
        res = reindex(roots, on_phase=lambda p: _set_state(phase=p))
        _set_state(last_result=res, phase="done")
    except Exception:
        _set_state(last_error=traceback.format_exc(), phase="error")
    finally:
        _set_state(indexing=False, finished_at=time.time())


@app.on_event("startup")
def _startup():
    # Make sure the index exists before any search runs
    ensure_index()


@app.get("/health")
def health():
    return {"ok": True, "index": INDEX_NAME}


@app.get("/status")
def status():
    # Expose lightweight state for the UI
    with _state_lock:
        return dict(_index_state)


@app.post("/index")
def start_index(req: IndexRequest):
    # Prevent concurrent runs
    with _state_lock:
        if _index_state["indexing"]:
            raise HTTPException(status_code=409, detail="Indexing already in progress")

    # Reset the index synchronously to avoid races with the background thread
    try:
        _set_state(phase="reset")
        reset_index()
    except Exception as ex:
        _set_state(phase="error", last_error=str(ex))
        raise HTTPException(status_code=503, detail=f"Failed to reset index: {ex}")

    # Launch reindex in background (non-blocking)
    t = threading.Thread(
        target=_run_reindex,
        args=(req.roots if (req and req.roots) else None,),
        daemon=True,
    )
    t.start()
    return {"started": True, "reset": True}


# ---------------------------
# Search helpers
# ---------------------------

# Characters that must be escaped for Lucene query_string
_RESERVED = r'+-!(){}[]^"~:\\/'

def _escape_for_query_string(q: str) -> str:
    """
    Prepare a user query for OpenSearch 'query_string' with these rules:
      - Exact tokens by default (we only search the 'content' field; no substring analyzer).
      - Wildcards: user '%' => single char, map to '?'; '*' kept as-is (any length).
      - Boolean operators AND/OR/NOT (case-insensitive) are preserved as standalone words.
      - All other Lucene-reserved characters are escaped.
    """
    if not q:
        return q

    # Normalize custom single-char wildcard
    q = q.replace('%', '?')

    # Split and preserve spaces
    tokens = re.split(r'(\s+)', q)

    def is_bool(tok: str) -> bool:
        t = tok.upper()
        return t in ("AND", "OR", "NOT")

    def esc(tok: str) -> str:
        if is_bool(tok):
            return tok.upper()
        # Escape reserved chars but keep wildcards * and ? intact
        out = []
        for ch in tok:
            if ch in _RESERVED:
                out.append('\\' + ch)
            else:
                out.append(ch)
        return ''.join(out)

    return ''.join(esc(t) if not t.isspace() else t for t in tokens)

@app.get("/doc")
def get_document(path: str = Query(..., description="Absolute path / document id")):
    """
    Return the full document by its id (we use absolute path as _id).
    """
    # Optional: block while indexing (keeps behavior consistent)
    with _state_lock:
        if _index_state.get("indexing"):
            raise HTTPException(status_code=423, detail="Indexing in progress")

    try:
        doc = client.get(index=INDEX_NAME, id=path)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Document not found")
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))

    src = doc.get("_source", {})
    return {
        "path": src.get("path"),
        "filename": src.get("filename"),
        "content": src.get("content", ""),
    }

@app.get("/search")
def search(q: str, limit: int = 10, offset: int = 0, highlight: bool = True):
    with _state_lock:
        if _index_state.get("indexing"):
            raise HTTPException(status_code=423, detail="Indexing in progress")
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="query string q is required")

    # Extract "quoted" phrases (case-sensitive) and remove them from the remaining query
    quoted_phrases = re.findall(r'"([^"]+)"', q)
    remaining_query = re.sub(r'"[^"]+"', " ", q)

    # Prepare remaining query: escape specials, map % -> ?, keep * for any-length
    safe_q = _escape_for_query_string(remaining_query.strip())

    must_clauses = []
    if safe_q:
        must_clauses.append({
            "query_string": {
                "query": safe_q,
                "fields": ["content"],          # case-insensitive tokens
                "default_operator": "AND",
                "analyze_wildcard": True
            }
        })

    for phrase in quoted_phrases:
        must_clauses.append({
            "match_phrase": {
                "content.cs": {                 # case-sensitive subfield
                    "query": phrase,
                    "slop": 0
                }
            }
        })

    body = {
        "from": offset,
        "size": limit,
        "track_total_hits": True,
        "query": {"bool": {"must": must_clauses}}
    }

    if highlight:
        body["highlight"] = {
            "fields": {"content": {}, "content.cs": {}},
            "pre_tags": ["<em>"], "post_tags": ["</em>"]
        }

    try:
        res = client.search(index=INDEX_NAME, body=body)
    except NotFoundError:
        ensure_index()
        return {"query": q, "hits": [], "total": 0}

    hits = []
    for h in res["hits"]["hits"]:
        snippet = None
        if highlight and h.get("highlight"):
            parts = []
            parts.extend(h["highlight"].get("content", []))
            parts.extend(h["highlight"].get("content.cs", []))
            if parts:
                snippet = "...".join(parts)
        if snippet is None:
            snippet = h["_source"].get("content", "")[:200]
        hits.append({"path": h["_source"]["path"], "filename": h["_source"]["filename"], "snippet": snippet})

    total = res["hits"]["total"]["value"] if isinstance(res["hits"]["total"], dict) else res["hits"]["total"]
    return {"query": q, "hits": hits, "total": total}

class ConfigUpdate(BaseModel):
    sql_source_paths: List[str] = Field(default_factory=list)

@app.get("/config")
def get_config():
    with _state_lock:
        indexing = bool(_index_state.get("indexing"))

    info = inspect_config()
    info["indexing"] = indexing
    try:
        info["doc_count"] = client.count(index=INDEX_NAME).get("count", 0)
    except Exception:
        info["doc_count"] = 0
    return info

@app.post("/config")
def update_config(payload: ConfigUpdate):
    # block config writes during indexing
    with _state_lock:
        if _index_state.get("indexing"):
            raise HTTPException(status_code=423, detail="Indexing in progress")
    try:
        res = save_config(payload.sql_source_paths)
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))
    # return fresh view
    info = inspect_config()
    info.update(res)
    return info