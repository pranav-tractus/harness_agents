from fastapi import APIRouter

from apps.api.models import ChatCreate, MessageIn
from apps.api.services import chat_service

router = APIRouter(prefix="/api/customers/{customer_id}/chats", tags=["chats"])


@router.get("")
def list_chats(customer_id: str) -> list[dict]:
    if not chat_service.list_chats(customer_id):
        chat_service.ensure_default_chat(customer_id)
    return chat_service.list_chats(customer_id)


@router.post("", status_code=201)
def create_chat(customer_id: str, body: ChatCreate) -> dict:
    return chat_service.create_chat(customer_id, body.title)


@router.get("/{chat_id}/messages")
def list_messages(customer_id: str, chat_id: str) -> list[dict]:
    return chat_service.list_messages(customer_id, chat_id)


@router.post("/{chat_id}/messages")
def post_message(customer_id: str, chat_id: str, body: MessageIn) -> dict:
    return chat_service.add_message(customer_id, chat_id, body.role, body.body)
