import os
import pathlib
import platform
import sys


files = sorted(pathlib.Path("demo-data/files").iterdir())
key = os.environ.get("GOOGLE_API_KEY")

print(f"Python Version: {platform.python_version()}")
print(f"Google API Key: {key}")
print(f"Demo Files: len={len(files)} files found")
print(f"Answer key       {'found' if pathlib.Path('demo-data/ground_truth.json').exists() else 'MISSING'}")
print(f"Master data      {'found' if pathlib.Path('demo-data/master.json').exists() else 'MISSING'}")
print(f"Gemini key       {'set' if key and key != 'your-gemini-api-key' else 'not set (steps 1 to 3 need it)'}")
import langchain, pypdf  # noqa: E402,F401  (proves the libraries are installed)
print(f"Libraries        langchain {langchain.__version__}, pypdf {pypdf.__version__}")