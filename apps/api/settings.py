import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Repo-root .env (MONGODB_URI / Atlas, LLM keys, etc.)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str
    mongo_db_name: str
    web_origin: str
    falkordb_host: str
    falkordb_port: int
    specs_s3_bucket: str
    vector_bucket: str
    vector_index: str
    aws_region: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        mongodb_uri=os.environ.get("MONGODB_URI", "mongodb://localhost:27017"),
        mongo_db_name=os.environ.get("MONGO_DB_NAME", "chat_sim"),
        web_origin=os.environ.get("WEB_ORIGIN", "http://localhost:5173"),
        falkordb_host=os.environ.get("FALKORDB_HOST", "localhost"),
        falkordb_port=int(os.environ.get("FALKORDB_PORT", "6379")),
        specs_s3_bucket=os.environ.get("SPECS_S3_BUCKET", ""),
        vector_bucket=os.environ.get("S3_VECTOR_BUCKET", ""),
        vector_index=os.environ.get("S3_VECTOR_INDEX", "product-catalog"),
        aws_region=os.environ.get("AWS_REGION", "us-east-1"),
    )
