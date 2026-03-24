# Process Behavior Profiler

A Python-based system profiling tool that monitors process-level CPU and memory usage over time and detects anomalous behavior such as CPU spikes and memory leak patterns.

## Features

- Continuous process monitoring at configurable intervals
- Time-series logging to CSV
- Baseline learning window for adaptive anomaly thresholds
- CPU spike detection (z-score based)
- Memory leak trend detection (positive slope over a rolling window)
- Top-N process tracking by CPU usage
- Summary report generation
- Works on Windows, Linux, and macOS (via `psutil`)
- Optional web dashboard for live monitoring and controls

## Requirements

- Python 3.10+
- Dependencies in `requirements.txt`

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Option A: Run CLI profiler (quick start)

```bash
python profiler.py --duration 60 --interval 1 --top-n 10 --output process_metrics.csv
```

Dry run (no CSV write):

```bash
python profiler.py --duration 20 --dry-run
```

---

## Option B: Run Web Dashboard (recommended)

Start web app:

```bash
uvicorn app:app --reload
```

Open in browser:

- `http://127.0.0.1:8000`

### Web workflow

1. Fill run parameters (interval, top-n, thresholds).
2. Click **Start**.
3. Watch live charts, latest samples, and alerts.
4. Click **Stop** when done.
5. If not in dry-run mode, check generated CSV file (default: `process_metrics.csv`).

---

## Windows setup (PowerShell)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --reload
```

---

## CSV Output Columns

- `timestamp`
- `pid`
- `name`
- `cpu_percent`
- `memory_mb`
- `cpu_anomaly`
- `memory_leak_suspected`
- `notes`

## Notes

- CPU percentages are sampled from `psutil` process CPU counters.
- Very short-lived processes may be sampled only once.
- This project is intended for profiling and engineering diagnostics, not endpoint security.
