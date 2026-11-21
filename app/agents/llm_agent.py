import os
import base64
import io
import logging
import mimetypes

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.schemas import Invoice

# pypdf logs noisy "incorrect startxref pointer" warnings for slightly malformed PDFs.
logging.getLogger("pypdf").setLevel(logging.ERROR)

agent = create_agent(
    ChatGoogleGenerativeAI(
        model=os.environ.get("MODEL_SMALL", "gemini-3.5-flash-lite")),
    tools=[],
    system_prompt="You are a helpful assistant that extracts structured data from supplier invoices. " \
    "You will be given an invoice as text and/or page images and you should return a JSON object with " \
    "the following fields: supplier_name, invoice_number, po_number, total. Only use values that " \
    "actually appear in the document. If a field is missing or unreadable, return null for that " \
    "field; never guess or invent a value.",
    response_format=ToolStrategy(Invoice)
)


def read_file(file_path: str) -> list:
    """Read a file and return it as a list of message content blocks."""

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    lower = file_path.lower()

    if lower.endswith((".jpg", ".jpeg", ".png")):
        mime = mimetypes.guess_type(file_path)[0] or "image/jpeg"
        with open(file_path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        return [{"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}]

    if lower.endswith(".pdf"):
        return read_pdf(file_path)

    with open(file_path, "r", encoding="utf-8") as f:
        return [{"type": "text", "text": f.read()}]


MIN_TEXT_CHARS = 30  # below this, treat a page as a scan with no usable text layer


def read_pdf(file_path: str) -> list:
    """Return PDF pages as content blocks: text where the page has a text layer,
    otherwise a rendered PNG image so the model can read the scan."""
    import pypdfium2 as pdfium
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    pdf = pdfium.PdfDocument(file_path)
    blocks = []
    try:
        for i, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if len(text) >= MIN_TEXT_CHARS:
                blocks.append({"type": "text", "text": f"[Page {i + 1}]\n{text}"})
                continue
            image = pdf[i].render(scale=2).to_pil()  # ~144 DPI
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            data = base64.b64encode(buf.getvalue()).decode()
            blocks.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}})
    finally:
        pdf.close()
    return blocks


def read_invoice(file_path: str) -> Invoice:
    result = agent.invoke({"messages": [HumanMessage(content=read_file(file_path))]})
    return result["structured_response"]


if __name__ == "__main__":
    import sys
    import glob

    if len(sys.argv) < 2:
        print("Usage: python -m app.agents.llm_agent <file_or_glob> [<file_or_glob> ...]")
        sys.exit(1)

    # Expand wildcards here so it works the same in cmd, PowerShell and bash.
    file_paths = []
    for arg in sys.argv[1:]:
        file_paths.extend(sorted(glob.glob(arg)) or [arg])

    for file_path in file_paths:
        print(f"=== {file_path} ===")
        try:
            invoice = read_invoice(file_path)
            print(invoice.model_dump_json(indent=4))
        except Exception as e:
            print(f"Error processing file {file_path}: {e}")

# Run from project root:
#   uv run --env-file .env python -m app.agents.llm_agent demo-data/files/0002_bundle_scan.pdf
