"""Start the API server.

Use this instead of calling uvicorn directly, at least on Windows.

psycopg refuses to run on Windows' default ProactorEventLoop, and uvicorn 0.36+
builds its loop with an explicit ``loop_factory``, which ignores the event loop
policy. So neither setting the policy nor calling uvicorn normally is enough:
the loop has to be supplied through uvicorn's own ``loop`` option, which is
what this script does.

Run ``uvicorn api.main:app`` directly and startup fails with an explicit
message pointing back here -- see ``platform_compat.assert_event_loop_is_usable``.

    python -m scripts.serve
    python -m scripts.serve --reload --port 8080
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from platform_compat import ensure_psycopg_compatible_event_loop  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Kognia agent API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    # Covers anything that reads the policy (the reload supervisor, mainly).
    ensure_psycopg_compatible_event_loop()

    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        app_dir=str(SRC),
        # The part that actually matters: uvicorn builds the loop from this
        # factory, ignoring the policy entirely.
        loop="platform_compat:new_selector_event_loop",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
