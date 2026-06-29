from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    import uvicorn

    from rag.retriever import ChromaRetriever

    port = int(os.environ.get("PORT", "8000"))
    retriever = ChromaRetriever()
    print(
        f"Starting API on 0.0.0.0:{port}; "
        f"vector_store_ready={retriever.ready} path={retriever.vector_store_path}",
        flush=True,
    )
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
