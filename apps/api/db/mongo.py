from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from apps.api.settings import get_settings

_client: MongoClient | None = None


def _get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(get_settings().mongodb_uri)
    return _client


def reset_client() -> None:
    global _client
    _client = None


def get_db() -> Database:
    return _get_client()[get_settings().mongo_db_name]


def customers() -> Collection:
    return get_db()["customers"]


def products() -> Collection:
    return get_db()["products"]


def messages() -> Collection:
    return get_db()["messages"]


def chats() -> Collection:
    return get_db()["chats"]


def summaries() -> Collection:
    return get_db()["summaries"]
