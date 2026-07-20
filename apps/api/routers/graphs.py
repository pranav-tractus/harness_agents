from fastapi import APIRouter

from apps.api.services import graph_reader_service

customer_router = APIRouter(prefix="/api/customers/{customer_id}", tags=["graphs"])
catalog_router = APIRouter(prefix="/api/graph", tags=["graphs"])


@customer_router.get("/graph")
def get_customer_graph(customer_id: str) -> dict:
    return graph_reader_service.read_customer_graph(customer_id)


@catalog_router.get("/products")
def get_product_graph() -> dict:
    return graph_reader_service.read_product_graph()
