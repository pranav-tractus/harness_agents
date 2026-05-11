"""Back-compat shim. New code should import from ``core.models``."""

from core.models import (  # noqa: F401
    LLMExtractContractProductItem,
    SOExtractContractList,
    SOUpdateContractList,
    SalesOrderExtractContractKeyDetails,
    SalesOrderUpdateContractKeyDetails,
    dict_to_items_type,
    dict_to_llm_details,
)
