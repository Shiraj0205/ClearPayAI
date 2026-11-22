"""Read a file and determine the format
of its content blocks (text or images).
"""

import base64
import os
import io
import json
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import List, Union

from pypdf import PdfReader
import pandas as pd

from app.agents.llm_agent import read_pdf


MIN_TEXT_CHARS_PER_PAGE = 50  # below this, treat a page as a scan with no usable text layer

class DocumentFormat:
    """Classify a document's content blocks as text or images."""
    DIGITAL_PDF = "digital_pdf"
    SCANNED_PDF = "scanned_pdf"
    IMAGE = "image"
    SPREADSHEET = "spreadsheet"
    GOV_JSON = "gov_json"
    UNKNOWN = "unknown"


@dataclass
class ReadResult:
    format: str
    page_texts: List[str] = field(default_factory=list)
    page_needing_vision: List[int] = field(default_factory=list)
    structured: dict | None = None

def detect_format(filename: str, data: bytes) -> str:
    """Detect the format of a document and return a ReadResult."""

    ext = PurePath(filename).suffix.lower()
    if ext == ".json":
            return DocumentFormat.GOV_JSON
    if ext in {".xls", ".xlsx", ".csv"}:
        return DocumentFormat.SPREADSHEET
    if ext in {".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff", ".bmp", ".webp"}:
        return DocumentFormat.IMAGE

    if ext == ".pdf" or data[:5] == b"%PDF":
        # Check if the PDF has a text layer or is just scanned images

        try:
            reader = PdfReader(io.BytesIO(data))
            texts = [(page.extract_text() or "").strip() for page in reader.pages]
        except Exception:
            return DocumentFormat.SCANNED_PDF
        
        if texts and all(len(t) < MIN_TEXT_CHARS_PER_PAGE for t in texts):
            return DocumentFormat.DIGITAL_PDF
        return DocumentFormat.SCANNED_PDF
    
    return DocumentFormat.UNKNOWN

def read_document(filename: str, data: bytes, max_pages: int = 60) -> ReadResult:
    """Read a document and return a ReadResult with its format and content blocks."""
    fmt = detect_format(filename, data)
    result = ReadResult(format=fmt)

    if fmt == DocumentFormat.GOV_JSON:
        return ReadResult(format=fmt, structured=parse_gov_json(data))

    if fmt == DocumentFormat.DIGITAL_PDF:
        reader = PdfReader(io.BytesIO(data))
        result.page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
    elif fmt == DocumentFormat.SCANNED_PDF:
        result.page_needing_vision = list(range(len(read_pdf(io.BytesIO(data)))))
    elif fmt == DocumentFormat.SPREADSHEET:
        try:
            df = pd.read_excel(io.BytesIO(data)) if filename.lower().endswith((".xls", ".xlsx")) else pd.read_csv(io.BytesIO(data))
            result.structured = df.to_dict(orient="records")
        except Exception:
            result.structured = None

    return result

def render_image(filename: str, data: bytes, page_index: int, scale: float = 2.0) -> bytes:
    """Return an HTML <img> tag with the image data embedded as a base64 URL."""
    fmt = detect_format(filename, data)
    if fmt == DocumentFormat.IMAGE:
        return data
    
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(io.BytesIO(data))
    page = pdf[page_index]
    image = page.render(scale=scale).to_pil()
    buf = io.BytesIO()
    image.convert("L").save(buf, format="PNG", optimize=True)
    return buf.getvalue()

def spreadsheet_to_text(filename: str, data: bytes) -> list[str]:
    """Convert a spreadsheet to text."""
    if filename.lower().endswith((".csv")):
        frames = {"Sheet1": pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False)}
    else:
        frames = pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=str, header=None, keep_default_na=False)

    pages = []
    for name, df in frames.items():
        df = df.fillna("").astype(str)
        pages.append(f"[sheet: {name}]\n" + df.to_csv(index=False, header=False))
    return pages
    
def spreadsheet_rows(filename: str, data: bytes, max_rows: int = 200, max_cols: int = 30) -> list[dict]:
    """Cells as strings, sheet by sheet, so the web screen can show the original (browsers cannot render Excel)."""
    if filename.lower().endswith(".csv"):
        frames = {"Sheet1": pd.read_csv(io.BytesIO(data), dtype=str, header=None)}
    else:
        frames = pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=str, header=None)
    sheets = []
    for name, df in frames.items():
        df = df.fillna("")
        sheets.append({"name": str(name), "rows": df.iloc[:max_rows, :max_cols].values.tolist(),
                       "truncated": df.shape[0] > max_rows or df.shape[1] > max_cols})
    return sheets

def parse_gov_json(data: bytes) -> dict:
    """Parse a government JSON document and return its structured data."""
    
    doc = json.loads(data)
    if "ItemList" in doc and "DocDtls" in doc:
        seller, buyer, dd, val = doc["SellerDtls"], doc.get("BuyerDtls", {}), doc["DocDtls"], doc["ValDtls"]
        lines = []
        for item in doc["ItemList"]:
            qty = float(item.get("Qty", 0))
            price = float(item.get("UnitPrice", 0))
            lines.append(
                {
                    "sku": item.get("PrdCd") or item.get("PrdDesc", ""),
                    "description": item.get("PrdDesc", ""),
                    "hsn": str(item.get("HsnCd", "")),
                    "qty_cartons": qty,
                    "price_per_carton": price,
                    "amount": float(item.get("AssAmt", qty * price)),
                }
            )

        rate = float(doc["ItemList"][0].get("GstRt", 0)) if doc["ItemList"] else 0.0
        tax = float(val.get("IgstVal", 0)) + float(val.get("CgstVal", 0)) + float(val.get("SgstVal", 0))
        data_out = {
            "supplier_name": seller.get("LglNm", ""),
            "supplier_gstin": seller["Gstin"],
            "buyer_gstin": buyer.get("Gstin", ""),
            "invoice_number": dd["No"],
            "invoice_date": _ddmmyyyy_to_iso(dd["Dt"]),
            "po_number": (doc.get("RefDtls", {}).get("PrecDocDtls") or [{}])[0].get("InvNo", "")
            or doc.get("RefDtls", {}).get("PoRef", ""),
            "eway_bill_number": str(doc.get("EwbDtls", {}).get("EwbNo", "") or ""),
            "vehicle_number": doc.get("EwbDtls", {}).get("VehNo", ""),
            "lines": lines,
            "subtotal": float(val["AssVal"]),
            "gst_rate": rate,
            "tax_amount": tax,
            "total": float(val["TotInvVal"]),
            "bank_account_present": bool(doc.get("PayDtls")),
            "confidence": 1.0,
            "uncertain_fields": [],
        }
        return {"doc_type": "invoice", "data": data_out}
    if "ewbNo" in doc:
        items = [
            {
                "hsn": str(i.get("hsnCode", "")),
                "qty_cartons": float(i.get("quantity", 0)),
                "taxable_value": float(i.get("taxableAmount", 0)),
            }
            for i in doc.get("itemList", [])
        ]
        veh = (doc.get("VehiclListDetails") or [{}])[0].get("vehicleNo", "") or doc.get("vehicleNo", "")
        data_out = {
            "eway_bill_number": str(doc["ewbNo"]),
            "generated_date": _ddmmyyyy_to_iso(doc.get("ewayBillDate", "").split(" ")[0]),
            "valid_until": _ddmmyyyy_to_iso(doc.get("validUpto", "").split(" ")[0]),
            "supplier_gstin": doc["fromGstin"],
            "recipient_gstin": doc.get("toGstin", ""),
            "invoice_number": doc.get("docNo", ""),
            "vehicle_number": veh,
            "items": items,
            "total_value": float(doc["totInvValue"]),
            "confidence": 1.0,
            "uncertain_fields": [],
        }
        return {"doc_type": "eway_bill", "data": data_out}
    raise ValueError("JSON is neither a GST e-invoice nor an e-way bill")


def _ddmmyyyy_to_iso(value: str) -> str:
    if not value:
        return ""
    parts = value.replace("-", "/").split("/")
    if len(parts) == 3 and len(parts[2]) == 4:
        return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
    return value
    





