from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    import uvicorn

    from rag.warmup import warmup_rag_stack

    port = int(os.environ.get("PORT", "8000"))
    warmup_state = warmup_rag_stack()
    print(
        f"Starting API on 0.0.0.0:{port}; "
        f"warmup_ready={warmup_state.completed} "
        f"warmup_seconds={warmup_state.duration_seconds} "
        f"vector_store_ready={warmup_state.details.get('vector_store_ready')} "
        f"path={warmup_state.details.get('vector_store_path')}",
        flush=True,
    )
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
