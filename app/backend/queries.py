from typing import List

def escape_lucene(s: str) -> str:
    """Escape Lucene query_string reserved characters in a plain term."""
    if not s:
        return s
    s = s.replace("\\", "\\\\")
    special = ['+', '-', '&&', '||', '!', '(', ')', '{', '}', '[', ']', '^', '"', '~', '*', '?', ':', '/']
    for ch in special:
        s = s.replace(ch, '\\' + ch)
    return s

def build_boolean_query(all_of: List[str] = None, any_of: List[str] = None, none_of: List[str] = None) -> str:
    """Programmatically build a Lucene query_string with AND/OR/NOT."""
    parts = []
    if all_of:
        parts.append(' AND '.join([escape_lucene(t) for t in all_of]))
    if any_of:
        parts.append('(' + ' OR '.join([escape_lucene(t) for t in any_of]) + ')')
    if none_of:
        parts.append(' '.join(['NOT ' + escape_lucene(t) for t in none_of]))
    return ' AND '.join([p for p in parts if p])
