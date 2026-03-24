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

## Architecture

The profiler is built from three core components:

1. **ProcessSampler**: Collects per-process CPU and RSS memory metrics.
2. **BehaviorAnalyzer**: Maintains rolling history and flags anomalies.
3. **ProfilerRunner**: Coordinates sampling, persistence, and reporting.

## Requirements

- Python 3.10+
- `psutil>=5.9`

Install dependency:

```bash
pip install -r requirements.txt
```

## Usage

Run for 60 seconds, sampling every second, and monitor top 10 processes:

```bash
python profiler.py --duration 60 --interval 1 --top-n 10 --output process_metrics.csv
```

Generate a dry run (collects and analyzes but does not write CSV):

```bash
python profiler.py --duration 20 --dry-run
```

Tune detection behavior:

```bash
python profiler.py \
  --cpu-z-threshold 2.5 \
  --memory-window 8 \
  --memory-leak-threshold-mb 3
```

## Windows Quick Start

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python profiler.py --duration 60 --interval 1 --top-n 10 --output process_metrics.csv
```

## Output

### CSV columns

- `timestamp`
- `pid`
- `name`
- `cpu_percent`
- `memory_mb`
- `cpu_anomaly`
- `memory_leak_suspected`
- `notes`

### Console summary

After completion, the tool prints:

- Total samples collected
- Number of unique processes observed
- CPU anomaly counts
- Memory leak suspicion counts
- Top flagged processes

## Notes

- CPU percentages are sampled from `psutil` process CPU counters.
- Very short-lived processes may be sampled only once.
- This project is intended for profiling and engineering diagnostics, not endpoint security.
