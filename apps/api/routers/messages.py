from fastapi import APIRouter

from apps.api.models import MessageIn
from apps.api.services import chat_service

router = APIRouter(prefix="/api/customers/{customer_id}/messages", tags=["messages"])


@router.get("")
def list_messages(customer_id: str) -> list[dict]:
    chat_id = chat_service.ensure_default_chat(customer_id)
    return chat_service.list_messages(customer_id, chat_id)


@router.post("")
def post_message(customer_id: str, body: MessageIn) -> dict:
    chat_id = chat_service.ensure_default_chat(customer_id)
    return chat_service.add_message(customer_id, chat_id, body.role, body.body)
