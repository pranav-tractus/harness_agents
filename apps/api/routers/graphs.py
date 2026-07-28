from fastapi import APIRouter

from apps.api.services import graph_reader_service

customer_router = APIRouter(prefix="/api/customers/{customer_id}", tags=["graphs"])


@customer_router.get("/graph")
def get_customer_graph(customer_id: str) -> dict:
    return graph_reader_service.read_customer_graph(customer_id)
