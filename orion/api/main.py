from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run("orion.api.app:app", host="127.0.0.1", port=8010, reload=False)
