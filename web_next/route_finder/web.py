from __future__ import annotations

import os
import sys

import uvicorn


def main() -> None:
    host = os.getenv("WEB_HOST", "127.0.0.1")
    port = int(os.getenv("WEB_PORT", os.getenv("PORT", "8000")))

    try:
        uvicorn.run(
            "route_finder.web_app:app",
            host=host,
            port=port,
            reload=False,
            log_level="info",
        )
    except OSError as exc:
        if getattr(exc, "winerror", None) == 10048 or exc.errno in (48, 98, 10048):
            print(
                f"\nPort {port} is already in use.\n"
                f"  • Open the app that's already running: http://{host}:{port}\n"
                f"  • Or use another port:  set WEB_PORT=8001  then run again\n"
                f"  • Or stop the other process (Windows): netstat -ano | findstr :{port}\n",
                file=sys.stderr,
            )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
