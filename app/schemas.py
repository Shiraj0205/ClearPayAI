from pydantic import BaseModel, Field


class Invoice(BaseModel):
    """Supplier invoice fields extracted from a document.

    Every field is optional so the model can return a real null when a value
    is not present in the document, instead of inventing one.
    """
    supplier_name: str | None = Field(None, description="The name of the supplier, or null if not shown")
    invoice_number: str | None = Field(None, description="The invoice number, or null if not shown")
    po_number: str | None = Field(None, description="The purchase order number, or null if not shown")
    total: float | None = Field(None, description="The total amount of the invoice, or null if not shown")
