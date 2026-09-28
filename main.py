from campusclaw.config import Config
from campusclaw.web import serve


if __name__ == "__main__":
    serve(Config.from_env())
