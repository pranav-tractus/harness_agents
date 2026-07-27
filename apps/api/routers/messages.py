from fastapi import APIRouter

from apps.api.models import MessageIn
from apps.api.services import agent_service, agent_tag, chat_service
from core.utils import DEFAULT_MODEL_KEY

router = APIRouter(prefix="/api/customers/{customer_id}/messages", tags=["messages"])


@router.get("")
def list_messages(customer_id: str) -> list[dict]:
    return chat_service.all_messages(customer_id)


@router.post("")
def post_message(customer_id: str, body: MessageIn) -> dict:
    """Append the message, and run the agent when the body tags it.

    An @agent tag is the only way to reach the agent — there is no separate
    command endpoint. The response shape is uniform: an ordinary message comes
    back as a one-element list with a null summary.
    """
    chat_id = chat_service.ensure_active_chat(customer_id)
    msg = chat_service.add_message(customer_id, chat_id, body.role, body.body)
    action = agent_tag.parse(body.body)
    if action is None:
        return {"messages": [msg], "summary": None}
    if action == "approve":
        result = agent_service.approve(customer_id)
    else:
        result = agent_service.invoke(customer_id, body.model_key or DEFAULT_MODEL_KEY)
    return {"messages": [msg, *result["messages"]], "summary": result["summary"]}
