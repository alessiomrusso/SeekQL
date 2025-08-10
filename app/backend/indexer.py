# app/backend/indexer.py
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

import yaml
from opensearchpy import OpenSearch, helpers
from opensearchpy.helpers import BulkIndexError

# ----------------------------
# Environment / defaults
# ----------------------------
OS_HOST = os.getenv("OS_HOST", "127.0.0.1")
OS_PORT = int(os.getenv("OS_PORT", "9200"))
INDEX_NAME = os.getenv("OS_INDEX", "sql_files")

BULK_CHUNK_SIZE = int(os.getenv("BULK_CHUNK_SIZE", "500"))
REQUEST_TIMEOUT = int(os.getenv("OS_REQUEST_TIMEOUT", "120"))

# ----------------------------
# Config loading (root-level seekql.config.yml)
# ----------------------------

def _project_root() -> Path:
    """
    When frozen (PyInstaller onefile), use the folder where the EXE lives.
    When running from source, project root is two levels up from this file (…/app/backend -> root).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]

# Determine config file path:
CFG_PATH = os.getenv("SEEKQL_CONFIG")
if CFG_PATH:
    CONFIG_FILE = Path(CFG_PATH).expanduser()
else:
    CONFIG_FILE = _project_root() / "seekql.config.yml"

_cfg = {}
if CONFIG_FILE.exists():
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        _cfg = yaml.safe_load(f) or {}

# Pull values with sane fallbacks
SQL_SOURCE_PATHS: List[Path] = [
    Path(p).expanduser() for p in _cfg.get("sql_source_paths", [])
]
INCLUDE_EXTENSIONS: Tuple[str, ...] = tuple(
    (ext if str(ext).startswith(".") else f".{ext}").lower()
    for ext in _cfg.get("include_extensions", [".sql"])
)
EXCLUDE_DIRS = set(d.lower() for d in _cfg.get("exclude_dirs", []))
MAX_FILE_SIZE_MB = int(_cfg.get("max_file_size_mb", os.getenv("MAX_FILE_SIZE_MB", 10)))

# ----------------------------
# OpenSearch client
# ----------------------------
client = OpenSearch(
    hosts=[{"host": OS_HOST, "port": OS_PORT}],
    use_ssl=False,
    verify_certs=False,
)

# ----------------------------
# Index lifecycle
# ----------------------------
def ensure_index() -> None:
    """
    Ensure the index exists with a mapping that supports:
      - content (standard analyzer, case-insensitive)
      - content.cs (custom analyzer without lowercase) for case-sensitive phrases
    """
    if client.indices.exists(index=INDEX_NAME):
        return

    body = {
        "settings": {
            "analysis": {
                "analyzer": {
                    "cs_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": []  # no lowercase -> case-sensitive
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "path": {"type": "keyword"},
                "filename": {"type": "keyword"},
                "content": {
                    "type": "text",
                    "fields": {
                        "cs": {"type": "text", "analyzer": "cs_analyzer"}
                    }
                },
            }
        }
    }
    client.indices.create(index=INDEX_NAME, body=body)


def reset_index() -> None:
    """Delete index if present, then recreate with current mapping."""
    try:
        if client.indices.exists(index=INDEX_NAME):
            client.indices.delete(index=INDEX_NAME, ignore=[400, 404])
    finally:
        ensure_index()

# ----------------------------
# File collection (stateless)
# ----------------------------
def _iter_sql_files(root: Path) -> Iterable[Path]:
    """
    Recursively yield files under 'root' matching INCLUDE_EXTENSIONS.
    Excludes directories by name (case-insensitive) using EXCLUDE_DIRS.
    """
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        # prune excluded dirs
        dirnames[:] = [d for d in dirnames if d.lower() not in EXCLUDE_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() in INCLUDE_EXTENSIONS:
                yield p


def collect_sql_files(roots: List[Union[str, Path]]) -> Tuple[List[Dict], int]:
    """
    Read ALL matching files (no delta). Returns (docs, scanned_count).
    Each document uses absolute path as _id for deterministic upserts.
    """
    docs: List[Dict] = []
    scanned = 0
    max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024

    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        for file in _iter_sql_files(root):
            try:
                st = file.stat()
            except Exception:
                continue
            scanned += 1
            if st.st_size > max_bytes:
                continue

            try:
                text = file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                text = ""

            abs_path = str(file.resolve())
            docs.append(
                {
                    "_id": abs_path,
                    "path": abs_path,
                    "filename": file.name,
                    "content": text,
                }
            )

    return docs, scanned

# ----------------------------
# Bulk indexing
# ----------------------------
def _bulk_actions(docs: List[Dict]):
    for d in docs:
        yield {
            "_op_type": "index",
            "_index": INDEX_NAME,
            "_id": d["_id"],
            "_source": {
                "path": d["path"],
                "filename": d["filename"],
                "content": d["content"],
            },
        }


def index_documents(docs: List[Dict]) -> Dict:
    """Index docs via helpers.bulk; returns summary dict."""
    if not docs:
        return {"indexed": 0, "errors": False, "error_items": []}

    try:
        success, details = helpers.bulk(
            client,
            _bulk_actions(docs),
            chunk_size=BULK_CHUNK_SIZE,
            request_timeout=REQUEST_TIMEOUT,
            refresh="wait_for",  # searchable when we return
        )
        return {"indexed": int(success), "errors": bool(details), "error_items": []}
    except BulkIndexError as bie:
        items = []
        for item in bie.errors[:10]:
            try:
                action = next(iter(item))
                info = item[action]
                items.append(f"{action}: {info.get('error')}")
            except Exception:
                items.append(str(item))
        return {"indexed": bie.count, "errors": True, "error_items": items}
    except Exception as ex:
        return {"indexed": 0, "errors": True, "error_items": [repr(ex)]}

# ----------------------------
# Public API
# ----------------------------
def reindex(
    roots: Optional[List[Union[str, Path]]] = None,
    on_phase: Optional[callable] = None,
) -> Dict:
    """
    Full reindex:
      - ensure index,
      - resolve roots from args or config,
      - collect all docs,
      - bulk upsert.
    """
    ensure_index()

    # Resolve roots: request parameter > config file
    root_paths = (
        [Path(p).expanduser() if not isinstance(p, Path) else p for p in roots]
        if roots
        else SQL_SOURCE_PATHS
    )

    if not root_paths:
        if on_phase:
            on_phase("done")
        return {
            "indexed": 0,
            "considered": 0,
            "scanned": 0,
            "errors": False,
            "error_items": [],
            "note": "No roots provided and seekql.config.yml has no sql_source_paths.",
        }

    if on_phase:
        on_phase("collect")
    docs, scanned = collect_sql_files(root_paths)

    if on_phase:
        on_phase("bulk")
    res = index_documents(docs)

    if on_phase:
        on_phase("done")

    out = dict(res)
    out["considered"] = len(docs)
    out["scanned"] = scanned
    return out
