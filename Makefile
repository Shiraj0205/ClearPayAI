PYTHON ?= python
VENV ?= .venv
PIP ?= $(VENV)/Scripts/pip

install_requirements:  ## install requirements into the virtual environment
	uv add -r requirements-dev.txt

setup:  ## create .env from the template
	@$(PYTHON) -c "import os,shutil; print('.env already exists') if os.path.exists('.env') else (shutil.copy('.env.example','.env'), print('Created .env: put your Gemini key in it'))"

IMAGE ?= clearpayai-steps:lab

# On Windows, make has no POSIX `sh` on PATH (and `bash` there is WSL's), so run
# run.sh through Git Bash explicitly. Override GIT_BASH if Git lives elsewhere.
ifeq ($(OS),Windows_NT)
GIT_BASH ?= C:/Program Files/Git/bin/bash.exe
RUN = "$(GIT_BASH)" ./run.sh
else
RUN = ./run.sh
endif

# Calls docker directly (not ./run.sh) so it works from PowerShell/cmd on Windows,
# where make has no POSIX `sh` on PATH.
build: setup  ## build the lab image
	docker build -q -t $(IMAGE) .

check: build  ## prove Docker, the papers and (if set) the key work
	$(RUN) check.py