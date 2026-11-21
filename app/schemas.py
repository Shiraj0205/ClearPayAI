from pydantic import BaseModel, Field
from typing import Literal
import os

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage


class Invoice(BaseModel):
    """Supplier invoice fields extracted from a document.

    Every field is optional so the model can return a real null when a value
    is not present in the document, instead of inventing one.
    """
    supplier_name: str | None = Field(None, description="The name of the supplier, or null if not shown")
    invoice_number: str | None = Field(None, description="The invoice number, or null if not shown")
    po_number: str | None = Field(None, description="The purchase order number, or null if not shown")
    total: float | None = Field(None, description="The total amount of the invoice, or null if not shown")


class DocumentType(BaseModel):
    """The type of document being processed."""
    documentType: Literal["invoice", "shipping", "certificate", "other"]

class Shipping(BaseModel):
    """Shipping document fields extracted from a document."""
    invoice_number: str | None = Field(None, description="The invoice number, or null if not shown")
    vehicle_number: str | None = Field(None, description="The vehicle number, or null if not shown")

class Certificate(BaseModel):
    """Certificate document fields extracted from a document."""
    batch_number: str | None = Field(None, description="The batch number, or null if not shown")
    expiry_date: str | None = Field(None, description="The expiry date of the certificate, or null if not shown")
    result: str | None = Field(None, description="The result of the certificate, or null if not shown")


