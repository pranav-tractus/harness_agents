from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routers import (
    chats,
    customers,
    graphs,
    messages,
    models_router,
    products,
)
from apps.api.settings import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="Chat Simulation API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[get_settings().web_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(customers.router)
    app.include_router(products.router)
    app.include_router(chats.router)
    app.include_router(messages.router)
    app.include_router(models_router.router)
    app.include_router(graphs.customer_router)
    return app


app = create_app()
