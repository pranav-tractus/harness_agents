from typing import List, Optional
from pydantic import BaseModel, Field
from pydantic.type_adapter import TypeAdapter


class LLMExtractContractProductItem(BaseModel):
    sr_no: int = Field(description="serial number for the product; for example 1, 2, 3, 4 ... etc")
    description: str = Field(description="Product name which it want to sell from chat messages. If not found it should be ''")
    quantity: Optional[float] = Field(description="Product quantity in floating point number. If not found it should be ''")
    quantity_unit: str = Field(description="Infer Product qauntity unit from chat in MT, KG etc in capital. If not found it should be """)
    unit_price: Optional[float] = Field(description="Product unit price for example USD/MT, SGD/MT, USD/KG, INR/MT etc in floating point number. If not found it should be ''")
    pricing_unit: str = Field(description="Infer Product pricing unit from chat in USD/MT, SGD/MT, USD/KG, INR/MT etc in capital. If not found it should be ''")
    ship_term: str = Field(description='The Shipment Terms can have only these values "EXW", "FOB", "CIF", "DDP" (find approriate value for the Shipment Terms from chat messages). If not found it should be ''')
    delivery_terms: str = Field(description='Per-product delivery terms including the incoterm and location, like CIF Busan or FOB Shanghai. If not found it should be ""')
    shipment_date: str = Field(description='Per-product shipment date in ISO format. If not found it should be ""')
    shipping_address: str = Field(description='Per-product shipping address or ship-to destination. If not found it should be ""')
    packing: str = Field(description='Extract Packing info from chat messages or from "Latest Packing and loading" for that particular product name from "counter party info". If not found it should be ''')
    loading: str = Field(description='Extract Loading info from chat messages or from "Latest Packing and loading" for that particular product name from "counter party info". If not found it should be ""')
    total: Optional[float] = Field(description='Total amount for the product quantity*unit_price, make sure the unit for quantity and unit_price matches. If unit_price or quantity not found it should be empty')


class SalesOrderExtractContractKeyDetails(BaseModel):
    items: List[LLMExtractContractProductItem] = Field(description="List of Products with their information")
    do_date: str = Field(description='Delivery date (or Shipment date) for the product. If not found it should be ""')
    po_date: str = Field(description='Sales order date. If not found it should be ""', default='')
    po_ref_no: str = Field(description='Sales order product ref number. If not found it should be ""', default='')
    vendor_name: str = Field(description='Vender name (or Seller) from "vender information" section. It is name of the "vender information". If not found it should be ""')

    payment_date: str = Field(description='Payment terms information, extract from "counter party info", do not extract Payment terms from chat messages. It is Approved Credit Term of the "counter party info". It is similar to 100% Advance or 30% Adv or 70% CAD or 100% CAD or Net 14 Days or Net 60 Days or Net 120 Days etc. If not found it should be ""')
    delivery_terms: str = Field(description='Delivery Terms of the product fetch from chat messages. If not found it should be ""')

    billing_address: str = Field(description='Bill To information, extract from "counter party info". It is name and business address seperated by comma from the "counter party info". If not found it should be ""')
    shipping_method: str = Field(description='Extract Shipping method mentioned in the chat messages like by air, by sea etc. If not found it should be ""')
    shipping_address: str = Field(description='Fetch Shipping address (or Ship To) from the "counter party info". It is address of the "counter party info". If not found it should be ""')


class SalesOrderUpdateContractKeyDetails(BaseModel):
    items: List[LLMExtractContractProductItem] = Field(description="List of Products with their information")
    do_date: str = Field(description='Delivery date (or Shipment date) for the product, extract from chat messages if exists. If not found it should be ""')
    po_date: str = Field(description='Sales order date, extract from chat messages if exists. If not found it should be ""', default='')
    po_ref_no: str = Field(description='Sales order product ref number, extract from chat messages if exists. If not found it should be ""', default='')
    vendor_name: str = Field(description='Vender name (or Seller), extract from chat messages if exists. If not found it should be ""')

    payment_date: str = Field(description='Payment terms information, extract from chat messages if exists. It is similar to 100% Advance or 30% Adv or 70% CAD or 100% CAD or Net 14 Days or Net 60 Days or Net 120 Days etc. If not found it should be "".')
    delivery_terms: str = Field(description='Delivery Terms of the product fetch from chat messages. If not found it should be ""')

    billing_address: str = Field(description='Bill To information, extract from chat messages if exists (It is a name and address seperated by comma) or from "counter party info". It is name and address seperated by comma from the "counter party info". If not found it should be ""')
    shipping_method: str = Field(description='Extract Shipping method mentioned in the chat messages like by air, by sea etc. If not found it should be ""')
    shipping_address: str = Field(description='Fetch Shipping address (or Ship To) from chat message if exists or from the "counter party info". It is address of the "counter party. If not found it should be ""')


class SOExtractContractList(BaseModel):
    data: List[SalesOrderExtractContractKeyDetails] = Field(description="List of contracts group by product name")


class SOUpdateContractList(BaseModel):
    data: List[SalesOrderUpdateContractKeyDetails] = Field(description="List of contracts group by product name")


def dict_to_items_type(items: List[dict]):
    ExtractedListAdapter = TypeAdapter(List[LLMExtractContractProductItem])
    return ExtractedListAdapter.validate_python(items)


def dict_to_llm_details(details: dict):
    ExtractedListAdapter = TypeAdapter(SalesOrderExtractContractKeyDetails)
    return ExtractedListAdapter.validate_python(details)
