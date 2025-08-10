# app/backend/indexer.py
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

# ----------------------------
# YAML (preserve comments/format with ruamel if available)
# ----------------------------
_YAML_RUAMEL = False
try:
    from ruamel.yaml import YAML  # type: ignore
    from ruamel.yaml.comments import CommentedMap, CommentedSeq  # type: ignore
    from ruamel.yaml.scalarstring import DoubleQuotedScalarString as DQ  # type: ignore

    _YAML_RUAMEL = True
    _yaml = YAML()
    # Keep user formatting as much as possible
    _yaml.preserve_quotes = True
    _yaml.width = 10_000           # avoid line wrapping
    _yaml.indent(mapping=2, sequence=2, offset=2)
    _yaml.default_flow_style = False
except Exception:
    # Fallback: PyYAML (will NOT preserve comments/formatting)
    import yaml as _yaml  # type: ignore
    CommentedMap = dict          # type: ignore
    CommentedSeq = list          # type: ignore
    DQ = str                     # type: ignore

# ----------------------------
# OpenSearch
# ----------------------------
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
# Project root / config path resolution
# ----------------------------
def _project_root() -> Path:
    """
    When frozen (PyInstaller onefile), use the folder where the EXE lives.
    When running from source, project root is two levels up from this file (.../app/backend -> root).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


CFG_PATH = os.getenv("SEEKQL_CONFIG")
CONFIG_FILE = Path(CFG_PATH).expanduser() if CFG_PATH else _project_root() / "seekql.config.yml"

# Default commented template used if we need to create a file on save (keeps your comments/layout)
_SEEKQL_TEMPLATE = """# SeekQL config

# One or more folders; each will be scanned recursively
sql_source_paths:
  - "C:/path/to/your/sql"

# Optional: which file extensions to index
include_extensions:
  - .sql

# Optional: skip directories by name (case-insensitive)
exclude_dirs:
  - node_modules
  - .git
  - __pycache__

# Optional: max file size (MB) to index
max_file_size_mb: 10
"""

def _load_config_obj() -> CommentedMap:
    """
    Load YAML into a ruamel CommentedMap when available (preserves comments/format).
    Falls back to plain dict with PyYAML.
    """
    if CONFIG_FILE.exists():
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            if _YAML_RUAMEL:
                data = _yaml.load(f)  # CommentedMap
                return data if isinstance(data, CommentedMap) else CommentedMap(data or {})
            else:
                import yaml as pyyaml  # type: ignore
                return CommentedMap(pyyaml.safe_load(f) or {})
    return CommentedMap()

def _dump_config_obj(obj: CommentedMap) -> None:
    """Write YAML back. With ruamel: preserves comments/format; with PyYAML: formatting/comments are lost."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        if _YAML_RUAMEL:
            _yaml.dump(obj, f)
        else:
            # PyYAML fallback (no comments preserved)
            try:
                import yaml as pyyaml  # type: ignore
                pyyaml.safe_dump(obj, f, sort_keys=False, allow_unicode=True)
            except Exception:
                # Last-resort dump
                f.write(str(obj))

_cfg: CommentedMap = _load_config_obj()

def _get_list(obj, key, default):
    v = obj.get(key, default)
    return list(v) if isinstance(v, (list, tuple)) else default

SQL_SOURCE_PATHS: List[Path] = [Path(p).expanduser() for p in _get_list(_cfg, "sql_source_paths", [])]
INCLUDE_EXTENSIONS: Tuple[str, ...] = tuple(
    (ext if str(ext).startswith(".") else f".{ext}").lower()
    for ext in _get_list(_cfg, "include_extensions", [".sql"])
)
EXCLUDE_DIRS = set(str(d).lower() for d in _get_list(_cfg, "exclude_dirs", []))
try:
    MAX_FILE_SIZE_MB = int(_cfg.get("max_file_size_mb", os.getenv("MAX_FILE_SIZE_MB", 10)))
except Exception:
    MAX_FILE_SIZE_MB = 10

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
                        "filter": []  # no lowercase -> case-sensitive tokens
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
# Config inspection / persistence
# ----------------------------
def inspect_config() -> Dict:
    items = []
    for p in (SQL_SOURCE_PATHS or []):
        rp = Path(p).expanduser()
        try:
            resolved = str(rp.resolve())
        except Exception:
            resolved = str(rp)
        items.append({
            "input": str(p),
            "resolved": resolved,
            "exists": rp.exists(),
            "is_dir": rp.is_dir() if rp.exists() else False,
        })
    return {
        "config_file": str(CONFIG_FILE),
        "config_present": CONFIG_FILE.exists(),
        "sql_source_paths": items,
        "include_extensions": list(INCLUDE_EXTENSIONS),
        "exclude_dirs": list(EXCLUDE_DIRS),
        "max_file_size_mb": MAX_FILE_SIZE_MB,
        "preserve_comments": _YAML_RUAMEL,
    }

def save_config(new_paths: List[str]) -> dict:
    """
    Update ONLY the sequence under 'sql_source_paths' IN-PLACE,
    preserving comments/spacing/ordering around it (when ruamel is available).
    Also keeps Windows paths quoted for readability.
    """
    global _cfg, SQL_SOURCE_PATHS

    cleaned_raw = [str(p).strip() for p in new_paths if str(p).strip()]

    # Keep quotes on Windows-like absolute paths (C:\...) for readability
    cleaned: List[str] = []
    for p in cleaned_raw:
        cleaned.append(p)

    # Ensure file exists with initial template (to preserve original formatting/comments)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(_SEEKQL_TEMPLATE, encoding="utf-8")

    cfg_obj: CommentedMap = _load_config_obj()

    if _YAML_RUAMEL:
        # IN-PLACE edit using CommentedSeq; preserve any end comment that sits between this key and the next
        seq = cfg_obj.get("sql_source_paths")
        if not isinstance(seq, CommentedSeq):
            seq = CommentedSeq(list())
            # If key existed as plain list earlier, reattach in same position
            cfg_obj["sql_source_paths"] = seq

        # Preserve the "end" comment (often the comment separating this key from the next)
        end_comment = getattr(seq.ca, "end", None)

        # Replace items in one go (slice assignment keeps node & comments)
        # Use DQ to keep quotes around paths
        seq[:] = [DQ(s) for s in cleaned]

        # Restore end comment if it existed
        if end_comment is not None:
            seq.ca.end = end_comment
    else:
        # Fallback: replace value (comments/formatting will be lost)
        cfg_obj["sql_source_paths"] = cleaned

    _dump_config_obj(cfg_obj)

    # Refresh in-memory snapshot from *current* object
    _cfg = cfg_obj
    # Convert possibly quoted scalars back to plain strings
    SQL_SOURCE_PATHS = [Path(str(p)).expanduser() for p in _get_list(_cfg, "sql_source_paths", [])]

    return {"ok": True, "count": len(SQL_SOURCE_PATHS)}

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
        success, _details = helpers.bulk(
            client,
            _bulk_actions(docs),
            chunk_size=BULK_CHUNK_SIZE,
            request_timeout=REQUEST_TIMEOUT,
            refresh="wait_for",  # searchable when we return
        )
        return {"indexed": int(success), "errors": False, "error_items": []}
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
def ensure_index_ready() -> None:
    """Alias kept for compatibility."""
    ensure_index()

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
