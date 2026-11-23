from pydantic import BaseModel, Field
from enum import Enum
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


class DocumentClassification(BaseModel):
    """The type of document being processed."""
    documentType: Literal["invoice", "shipping", "certificate", "other"]


class DocumentType(str, Enum):
    invoice = "invoice"
    packing_list = "packing_list"
    lorry_receipt = "lorry_receipt"
    eway_bill = "eway_bill"
    quality_certificate = "quality_certificate"
    credit_note = "credit_note"
    debit_note = "debit_note"

class Shipping(BaseModel):
    """Shipping document fields extracted from a document."""
    invoice_number: str | None = Field(None, description="The invoice number, or null if not shown")
    vehicle_number: str | None = Field(None, description="The vehicle number, or null if not shown")

class Certificate(BaseModel):
    """Certificate document fields extracted from a document."""
    batch_number: str | None = Field(None, description="The batch number, or null if not shown")
    expiry_date: str | None = Field(None, description="The expiry date of the certificate, or null if not shown")
    result: str | None = Field(None, description="The result of the certificate, or null if not shown")


DOC_FAMILY = {
    DocumentType.invoice: "invoice",
    DocumentType.packing_list: "shipping",
    DocumentType.lorry_receipt: "shipping",
    DocumentType.eway_bill: "shipping",
    DocumentType.quality_certificate: "quality",
    DocumentType.credit_note: "adjustment",
    DocumentType.debit_note: "adjustment",
}


class _Base(BaseModel):
    confidence: float = Field(
        ge=0, le=1, description="Your overall confidence that every field is correct (0-1). Be honest."
    )
    uncertain_fields: list[str] = Field(
        default_factory=list, description="Names of fields you could not read clearly."
    )


# --- classifier ---------------------------------------------------------------
class Segment(BaseModel):
    doc_type: DocumentType
    start_page: int = Field(ge=1, description="First page (1-based) of this document")
    end_page: int = Field(ge=1, description="Last page (1-based, inclusive)")
    reason: str = Field(description="Short reason, e.g. 'title says TAX INVOICE'")


class Classification(BaseModel):
    segments: list[Segment] = Field(description="Every page must belong to exactly one segment, in order.")
    confidence: float = Field(ge=0, le=1)


# --- invoice --------------------------------------------------------------------
class InvoiceLine(BaseModel):
    sku: str = Field(description="Item code / SKU exactly as printed")
    description: str = ""
    hsn: str = ""
    qty_cartons: float = Field(description="Quantity in cartons/cases")
    price_per_carton: float
    amount: float = Field(description="Line amount before tax")


class InvoiceData(_Base):
    supplier_name: str
    supplier_gstin: str = Field(description="15-character GSTIN of the seller")
    buyer_gstin: str = ""
    invoice_number: str
    invoice_date: str = Field(description="ISO date YYYY-MM-DD")
    po_number: str = Field(default="", description="Buyer purchase order number, e.g. PO-12345")
    eway_bill_number: str = ""
    vehicle_number: str = ""
    lines: list[InvoiceLine]
    subtotal: float
    gst_rate: float = Field(description="GST rate in percent, e.g. 18")
    tax_amount: float
    total: float
    bank_account_present: bool = Field(default=False, description="True if bank details are printed")


# --- shipping documents ----------------------------------------------------------
class PackingLine(BaseModel):
    sku: str
    qty_cartons: float
    batch_number: str = ""
    gross_weight_kg: float = 0


class PackingListData(_Base):
    supplier_gstin: str = ""
    packing_list_number: str
    invoice_number: str = ""
    po_number: str = ""
    lines: list[PackingLine]
    total_cartons: float
    total_weight_kg: float = 0


class LorryReceiptData(_Base):
    transporter_name: str
    lr_number: str = Field(description="Lorry receipt / bill of lading number")
    lr_date: str = ""
    vehicle_number: str
    consignor_gstin: str = ""
    consignee_gstin: str = ""
    invoice_number: str = ""
    packages: float = Field(description="Number of packages/cartons carried")
    weight_kg: float = 0


class EwayItem(BaseModel):
    hsn: str
    qty_cartons: float = 0
    taxable_value: float = 0


class EwayBillData(_Base):
    eway_bill_number: str = Field(description="12-digit e-way bill number")
    generated_date: str = ""
    valid_until: str = ""
    supplier_gstin: str
    recipient_gstin: str = ""
    invoice_number: str = ""
    vehicle_number: str = ""
    items: list[EwayItem] = Field(default_factory=list)
    total_value: float = Field(description="Total invoice value including tax")


# --- quality ---------------------------------------------------------------------
class QualityCertificateData(_Base):
    certificate_number: str
    supplier_gstin: str = ""
    sku: str = ""
    batch_number: str
    manufacture_date: str = ""
    expiry_date: str = Field(description="ISO date YYYY-MM-DD")
    result: str = Field(description="PASS or FAIL")


# --- adjustments -----------------------------------------------------------------
class AdjustmentNoteData(_Base):
    note_number: str
    note_type: str = Field(description="credit or debit")
    supplier_gstin: str
    original_invoice_number: str
    amount: float = Field(description="Total adjustment including tax")
    reason: str = ""


SCHEMA_BY_TYPE: dict[DocumentType, type[_Base]] = {
    DocumentType.invoice: InvoiceData,
    DocumentType.packing_list: PackingListData,
    DocumentType.lorry_receipt: LorryReceiptData,
    DocumentType.eway_bill: EwayBillData,
    DocumentType.quality_certificate: QualityCertificateData,
    DocumentType.credit_note: AdjustmentNoteData,
    DocumentType.debit_note: AdjustmentNoteData,
}


# --- reconciliation / exceptions -------------------------------------------------
class ReconciliationReport(BaseModel):
    decision: str = Field(description="'clean' if nothing needs a person, otherwise 'exception'")
    summary: str = Field(description="Two or three plain-English sentences a finance clerk understands")
    linked_document_ids: list[str] = Field(default_factory=list, description="Orphan documents you linked")


class SupervisorDecision(BaseModel):
    route: str = Field(description="'auto_approve', 'investigate' or 'human_review'")
    summary: str
    confidence: float = Field(ge=0, le=1)


class ExceptionFinding(BaseModel):
    finding: str = Field(description="What is wrong, in plain words, citing the documents")
    root_cause: str = Field(description="Most likely cause, e.g. 'short loading at supplier'")
    recommended_action: str
    similar_case_ids: list[int] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
