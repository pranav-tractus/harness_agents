"""Builders for the core sales-order contract models used across API tests.

The core models (``core.models``) require every field to be supplied, so these
helpers fill sensible defaults and let each test override only what it asserts on.
"""
from core.models import (
    LLMExtractContractProductItem,
    SalesOrderExtractContractKeyDetails,
    SalesOrderUpdateContractKeyDetails,
    SOExtractContractList,
    SOUpdateContractList,
)


def make_item(**over) -> LLMExtractContractProductItem:
    base = dict(
        sr_no=1,
        description="TG-BPPC",
        quantity=10.0,
        quantity_unit="MT",
        unit_price=None,
        pricing_unit="",
        ship_term="",
        delivery_terms="",
        shipment_date="",
        shipping_address="",
        packing="",
        loading="",
        total=None,
    )
    base.update(over)
    return LLMExtractContractProductItem(**base)


def _details_kwargs(items, over) -> dict:
    base = dict(
        items=items or [make_item()],
        vendor_name="",
        payment_date="",
        delivery_terms="",
        billing_address="",
        shipping_method="",
        shipping_address="",
    )
    base.update(over)
    return base


def make_extract(items=None, **over) -> SOExtractContractList:
    details = SalesOrderExtractContractKeyDetails(**_details_kwargs(items, over))
    return SOExtractContractList(data=[details])


def make_update(items=None, **over) -> SOUpdateContractList:
    details = SalesOrderUpdateContractKeyDetails(**_details_kwargs(items, over))
    return SOUpdateContractList(data=[details])
