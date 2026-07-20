import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str
    mongo_db_name: str
    web_origin: str
    falkordb_host: str
    falkordb_port: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        mongodb_uri=os.environ.get("MONGODB_URI", "mongodb://localhost:27017"),
        mongo_db_name=os.environ.get("MONGO_DB_NAME", "chat_sim"),
        web_origin=os.environ.get("WEB_ORIGIN", "http://localhost:5173"),
        falkordb_host=os.environ.get("FALKORDB_HOST", "localhost"),
        falkordb_port=int(os.environ.get("FALKORDB_PORT", "6379")),
    )
