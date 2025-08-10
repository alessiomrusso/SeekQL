# app/backend/indexer.py
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

import yaml
from opensearchpy import OpenSearch, helpers
from opensearchpy.helpers import BulkIndexError

# ----------------------------
# Environment / configuration
# ----------------------------
OS_HOST = os.getenv("OS_HOST", "localhost")
OS_PORT = int(os.getenv("OS_PORT", "9200"))
INDEX_NAME = os.getenv("OS_INDEX", "sql_files")

BULK_CHUNK_SIZE = int(os.getenv("BULK_CHUNK_SIZE", "500"))
REQUEST_TIMEOUT = int(os.getenv("OS_REQUEST_TIMEOUT", "120"))
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "10"))  # skip files larger than this

CONFIG_FILE = Path(__file__).with_name("config.yml")

# Load YAML config (optional)
if CONFIG_FILE.exists():
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        _cfg = yaml.safe_load(f) or {}
else:
    _cfg = {}

SQL_SOURCE_PATHS: List[Path] = [Path(p).expanduser() for p in _cfg.get("sql_source_paths", [])]
INCLUDE_EXTENSIONS: Tuple[str, ...] = tuple(
    (ext if ext.startswith(".") else f".{ext}").lower()
    for ext in _cfg.get("include_extensions", [".sql"])
)
EXCLUDE_DIRS: set = set(d.lower() for d in _cfg.get("exclude_dirs", []))

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
    Ensure the target index exists with a mapping that includes a case-sensitive subfield:
      - content       : text (standard analyzer, case-insensitive)
      - content.cs    : text (custom analyzer without lowercase) for quoted searches
    """
    if client.indices.exists(index=INDEX_NAME):
        return
    client.indices.create(
        index=INDEX_NAME,
        body={
            "settings": {
                "analysis": {
                    "analyzer": {
                        "cs_analyzer": {  # case-preserving analyzer for "content.cs"
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": []  # no lowercase filter => case-sensitive
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
                            "cs": {
                                "type": "text",
                                "analyzer": "cs_analyzer"
                            }
                        }
                    }
                }
            }
        }
    )


def reset_index() -> None:
    """Delete the index if it exists, then recreate with current mapping."""
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
    Walk 'root' recursively, pruning excluded directories, yielding files
    whose suffix matches INCLUDE_EXTENSIONS.
    """
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        # prune excluded dirs (by name, case-insensitive)
        dirnames[:] = [d for d in dirnames if d.lower() not in EXCLUDE_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() in INCLUDE_EXTENSIONS:
                yield p


def collect_sql_files(roots: List[Union[str, Path]]) -> Tuple[List[Dict], int]:
    """
    Read ALL matching files (no delta). Returns (docs, scanned_count).
    Each document _id is the absolute path, so reindexing upserts deterministically.
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
            if st.st_size > max_bytes:
                # skip huge files
                scanned += 1
                continue

            try:
                text = file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                text = ""

            abs_path = str(file.resolve())
            docs.append(
                {
                    "_id": abs_path,         # stable id -> upsert
                    "path": abs_path,
                    "filename": file.name,
                    "content": text,
                }
            )
            scanned += 1

    return docs, scanned

# ----------------------------
# Bulk indexing
# ----------------------------
def _bulk_actions(docs: List[Dict]) -> Iterable[Dict]:
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
    """
    Index provided docs via helpers.bulk; returns summary.
    """
    if not docs:
        return {"indexed": 0, "errors": False, "error_items": []}

    try:
        success, details = helpers.bulk(
            client,
            _bulk_actions(docs),
            chunk_size=BULK_CHUNK_SIZE,
            request_timeout=REQUEST_TIMEOUT,
            refresh="wait_for",  # make docs searchable when we return
        )
        return {"indexed": int(success), "errors": bool(details), "error_items": []}
    except BulkIndexError as bie:
        error_items = []
        for item in bie.errors[:10]:  # cap error echo
            try:
                action = next(iter(item))
                info = item[action]
                error_items.append(f"{action}: {info.get('error')}")
            except Exception:
                error_items.append(str(item))
        return {"indexed": bie.count, "errors": True, "error_items": error_items}
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
    Full reindex (stateless):
      - ensure index exists,
      - collect ALL docs from roots (no delta),
      - bulk upsert.
    """
    ensure_index()

    root_paths = [Path(p).expanduser() if not isinstance(p, Path) else p for p in (roots or SQL_SOURCE_PATHS)]
    if not root_paths:
        if on_phase: on_phase("done")
        return {
            "indexed": 0,
            "considered": 0,
            "scanned": 0,
            "errors": False,
            "error_items": [],
            "note": "No roots provided and config.yml has no sql_source_paths.",
        }

    if on_phase: on_phase("collect")
    docs, scanned = collect_sql_files(root_paths)

    if on_phase: on_phase("bulk")
    res = index_documents(docs)

    if on_phase: on_phase("done")
    out = dict(res)
    out["considered"] = len(docs)
    out["scanned"] = scanned
    return out
