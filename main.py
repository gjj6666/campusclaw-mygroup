import sys

from campusclaw.config import Config
from campusclaw.web import Application, serve


if __name__ == "__main__":
    config = Config.from_env()
    if len(sys.argv) == 2 and sys.argv[1] == "backfill":
        if config.validate_rag():
            raise SystemExit("RAG configuration incomplete")
        app = Application(config)
        try:
            print(app.rag.backfill())
        finally:
            app.close()
    elif len(sys.argv) == 1:
        serve(config)
    else:
        raise SystemExit("usage: python main.py [backfill]")
