from fastapi import APIRouter

from core.utils import MODEL_CATALOG

from apps.api.models import ModelOption

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("")
def list_models() -> list[ModelOption]:
    out = []
    for key, meta in sorted(MODEL_CATALOG.items()):
        out.append(ModelOption(
            key=key,
            display_name=meta["display_name"],
            provider=meta["provider"],
        ))
    return out
