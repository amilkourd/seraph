"""Run the three replicas in one process: dispatch :8101, report :8102, occupants :8103.

    uv run python run.py              # all three
    uv run python run.py occupants    # only some
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
import sys

import uvicorn

from legacy import dispatch, occupants, report
from legacy.common import env

APPS = {"dispatch": (dispatch.app, 8101), "report": (report.app, 8102), "occupants": (occupants.app, 8103)}


class Server(uvicorn.Server):
    @contextlib.contextmanager
    def capture_signals(self):  # one handler for all three servers, installed in main()
        yield


async def main(names: list[str]) -> None:
    host = env("REPLICAS_HOST", "127.0.0.1")
    servers = [Server(uvicorn.Config(APPS[n][0], host=host, port=APPS[n][1], log_level="info", access_log=True))
               for n in names]
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: [setattr(s, "should_exit", True) for s in servers])
    await asyncio.gather(*(s.serve() for s in servers))


if __name__ == "__main__":
    selected = sys.argv[1:] or list(APPS)
    unknown = [n for n in selected if n not in APPS]
    if unknown:
        sys.exit(f"unknown replica(s): {', '.join(unknown)} — choose from {', '.join(APPS)}")
    asyncio.run(main(selected))
