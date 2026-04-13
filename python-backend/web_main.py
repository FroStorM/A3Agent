import argparse
import os

import uvicorn


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")


def parse_args():
    parser = argparse.ArgumentParser(description="Run A3Agent in browser/server mode.")
    parser.add_argument("--host", default=os.environ.get("GA_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("GA_PORT", "8000")))
    parser.add_argument(
        "--workspace",
        default=os.environ.get("GA_WORKSPACE_ROOT", PROJECT_ROOT),
    )
    parser.add_argument(
        "--no-frontend",
        action="store_true",
        help="Disable serving the frontend static site and expose API only.",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn reload for local development.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.workspace:
        os.environ["GA_WORKSPACE_ROOT"] = os.path.abspath(os.path.expanduser(args.workspace))

    os.environ["GA_SERVE_FRONTEND"] = "0" if args.no_frontend else "1"
    if os.path.exists(os.path.join(DEFAULT_FRONTEND_DIR, "index.html")):
        os.environ.setdefault("GA_FRONTEND_DIR", DEFAULT_FRONTEND_DIR)

    uvicorn.run(
        "api_server:app",
        host=args.host,
        port=args.port,
        log_level="info",
        reload=args.reload,
        reload_dirs=[os.path.dirname(__file__)] if args.reload else None,
    )


if __name__ == "__main__":
    main()
