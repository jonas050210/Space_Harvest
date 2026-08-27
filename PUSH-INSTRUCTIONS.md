# Push / restore instructions

This Arena session worked on the fixed branch:

```text
arena/01a0418d-asteroid-colony-proto
```

If GitHub credentials are connected in the sandbox, the agent pushes directly:

```bash
git push origin arena/01a0418d-asteroid-colony-proto
```

If you are doing it locally instead:

```bash
git clone https://github.com/jonas050210/asteroid-colony-proto.git
cd asteroid-colony-proto
git checkout arena/01a0418d-asteroid-colony-proto  # if the branch exists remotely
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m src.main --headless --sim-days 6000
.venv/bin/python -m src.main
```

If you need a zip archive from this workspace, create it without the virtualenv:

```bash
zip -r asteroid-colony-proto-delivery.zip . -x ".venv/*" ".git/*" "__pycache__/*" "*/__pycache__/*" ".pytest_cache/*" "*/.pytest_cache/*"
```

No tokens or credentials are stored in this repository.
