from fastapi import APIRouter

from apps.api.models import AgentInvokeIn, CommandIn
from apps.api.services import chat_service, command_service

router = APIRouter(prefix="/api/customers/{customer_id}/commands", tags=["commands"])


@router.post("")
def run_command(customer_id: str, body: CommandIn) -> dict:
    chat_id = chat_service.ensure_default_chat(customer_id)
    chat_service.add_message(customer_id, chat_id, "me", f"/{body.command} {body.args or ''}".strip(),
                             kind="command")
    return command_service.dispatch(customer_id, body.command, body.args, body.model_key)


agent_router = APIRouter(prefix="/api/customers/{customer_id}/agent", tags=["agent"])


@agent_router.post("")
def run_agent(customer_id: str, body: AgentInvokeIn) -> dict:
    if body.action == "approve":
        return command_service.approve(customer_id)
    return command_service.invoke_agent(customer_id, body.model_key)
