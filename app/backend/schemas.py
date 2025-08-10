from pydantic import BaseModel
from typing import List, Optional

class SearchResult(BaseModel):
    path: str
    filename: str
    snippet: Optional[str]

class IndexRequest(BaseModel):
    roots: Optional[List[str]] = None  # optional; if omitted we use config.yml
