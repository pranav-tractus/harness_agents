"""Dev launcher: FastAPI (uvicorn) + Vite React dev server together.

    python run.py

One Ctrl+C stops both. Requires MongoDB reachable at MONGODB_URI and
`npm install` already run inside apps/web.
"""
import signal
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "apps" / "web"


def main() -> None:
    load_dotenv(ROOT / ".env")
    procs = []
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "apps.api.main:app", "--reload", "--port", "8000"],
        cwd=ROOT,
    )
    procs.append(api)
    web = subprocess.Popen(["npm", "run", "dev"], cwd=WEB)
    procs.append(web)

    def _shutdown(*_):
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    while True:
        for p in procs:
            code = p.poll()
            if code is not None:
                _shutdown()
        try:
            api.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass


if __name__ == "__main__":
    main()
