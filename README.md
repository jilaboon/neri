# CB2T MVP

Working vertical slice for CB2T manager MVP:
- Create/load project topology profile
- Simulate BPort discovery/connectivity
- Start BER test run (PRBS), monitor progress
- Persist run + lane-level results in SQLite
- Basic operator UI for demo flow

API options:
- `/api/tests/start` runs asynchronously (UI polling flow)
- `/api/tests/run-now` runs synchronously (deterministic smoke/demo automation)

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open: `http://127.0.0.1:8000`

## Windows EXE + ZIP (with demo files)

Automated in GitHub Actions: `.github/workflows/windows-package.yml`

How to build:
1. Push this repo to GitHub.
2. Open **Actions** tab.
3. Run **Build Windows Package** workflow (or push to `main`).
4. Download artifact: `CB2TManager-win64.zip`.

ZIP includes:
- `CB2TManager.exe`
- `demo/topology-demo.json`
- `demo/topology-demo.csv`
- `README.txt`

## Current MVP Boundaries

Included:
- Single-node manager app
- Simulated hardware integration layer
- Local result DB
- Operator-facing test run flow

Deferred:
- Real MQTT/BPort protocol integration
- MES integration
- Role-based access controls
- Advanced diagnostics (eye/fec/histogram)
- Cloud analytics pipeline
