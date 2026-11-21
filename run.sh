
cd "$(dirname "$0")" || exit 1
[ -f .env ] || cp .env.example .env
docker build -q -t clearpayai-steps:lab . >/dev/null || { echo "Docker build failed: is Docker Desktop running?"; exit 1; }
exec docker run --rm --env-file .env -v "$PWD:/app" -w /app -e PYTHONPATH=/app clearpayai-steps:lab python "$@"


#-----------------Commands LLM Agent--------------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------------
# Command to run the LLM agent with a specific PDF file:
# uv run --env-file .env python -m app.agents.llm_agent demo-data/files/0002_bundle_scan.pdf
# Run multiple files:
# uv run --env-file .env python -m app.agents.llm_agent demo-data/files/0002_* demo-data/files/0010_*
#---------------------------------------------------------------------------------------------------------



#-----------------Commands Classification Agent--------------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------------
# Command to run the classification agent with a specific PDF file:
# uv run --env-file .env python -m app.agents.classification_agent demo-data/files/0002_bundle_scan.pdf
# Run multiple files:
# uv run --env-file .env python -m app.agents.classification_agent demo-data/files/0002_* demo-data/files/0010_*
#---------------------------------------------------------------------------------------------------------