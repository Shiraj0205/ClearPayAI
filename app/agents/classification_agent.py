
import glob
import hashlib
import os
import sys
import json
import base64
from pydantic import BaseModel

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.schemas import Invoice, Shipping, Certificate, DocumentClassification
from app.agents.llm_agent import read_file

MODEL = ChatGoogleGenerativeAI(
    model=os.environ.get("MODEL_SMALL", "gemini-3.5-flash-lite")
)
SAVED = os.environ.get("SAVED_RESULTS", "app/agents/saved_results.jsonl")

FORMS = {
    "invoice": Invoice,
    "shipping": Shipping,
    "certificate": Certificate,
    "other": BaseModel
}

def ask(form, instructions, content: list) -> BaseModel:
    """Ask the model to fill out a form from a list of messages."""
    agent = create_agent(
        ChatGoogleGenerativeAI(
            model=os.environ.get("MODEL_SMALL", "gemini-3.5-flash-lite")),
        tools=[],
        system_prompt=instructions,
        response_format=ToolStrategy(form)
    )
    result = agent.invoke({"messages": HumanMessage(content=content)})["structured_response"]
    return result


def document_already_classified() -> dict:
    """Ask the model to classify a document type from a list of messages."""
    if not os.path.exists(SAVED):
        return {}

    done = {}
    with open(SAVED, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if "fields" not in row:  # legacy rows stored fields flat at the top level
                meta = {"file", "sha256", "document_type"}
                row = {**{k: row.get(k) for k in meta},
                       "fields": {k: v for k, v in row.items() if k not in meta}}
            done[row["sha256"]] = row
    return done


def read_document(file_path: str) -> list:
    """Read a document and return it as a list of message content blocks."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    data = open(file_path, "rb").read()
    fingerprint = hashlib.sha256(data).hexdigest()
    done = document_already_classified()

    if fingerprint in done:
        print(f"Document already classified: {file_path} (SHA256: {fingerprint})")
        return {**done[fingerprint], "skipped": True}

    content = read_file(file_path)
    document_type = ask(DocumentClassification, "Classify the type of document being processed.", content).documentType
    fields = ask(FORMS[document_type], f"Extract structured data from a {document_type} document.", content).model_dump() if document_type in FORMS else {}
    row = { 
        "file": os.path.basename(file_path), 
        "sha256": fingerprint, 
        "document_type": document_type, 
        "fields": fields
    }
    with open(SAVED, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")

    return row

if __name__ == "__main__":
    # Expand wildcards ourselves: cmd.exe/PowerShell pass "0002_*" through literally.
    paths = [p for arg in sys.argv[1:] for p in (sorted(glob.glob(arg)) or [arg])]
    for path in paths:
        result = read_document(path)
        print(f"{result['file']:24} {result['document_type']:12} {result['fields']}" + (" (skipped: seen before)" if result.get("skipped") else ""))
