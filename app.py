#!/usr/bin/env python3
"""Web dashboard for Process Behavior Profiler."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.requests import Request

from profiler import BehaviorAnalyzer, CsvLogger, ProcessSampler


class RunConfig(BaseModel):
    interval: float = Field(default=1.0, ge=0.2, le=30)
    top_n: int = Field(default=10, ge=1, le=100)
    baseline_window: int = Field(default=10, ge=3, le=200)
    cpu_z_threshold: float = Field(default=3.0, ge=0.5, le=20)
    memory_window: int = Field(default=6, ge=3, le=200)
    memory_leak_threshold_mb: float = Field(default=2.0, ge=0.1, le=1024)
    output: str = "process_metrics.csv"
    dry_run: bool = False


class ProfilerService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._running = False
        self._started_at: Optional[str] = None
        self._config = RunConfig()

        self.samples: Deque[Dict] = deque(maxlen=5000)
        self.alerts: Deque[Dict] = deque(maxlen=1000)
        self.summary: Dict = {
            "total_samples": 0,
            "unique_processes": 0,
            "cpu_anomalies": 0,
            "memory_leak_suspicions": 0,
            "top_cpu_anomaly_processes": [],
            "top_memory_leak_processes": [],
        }

    def status(self) -> Dict:
        with self._lock:
            return {
                "running": self._running,
                "started_at": self._started_at,
                "config": self._config.model_dump(),
                "summary": self.summary,
                "sample_buffer_size": len(self.samples),
                "alert_buffer_size": len(self.alerts),
            }

    def start(self, config: RunConfig) -> None:
        with self._lock:
            if self._running:
                raise RuntimeError("Profiler is already running")

            self._config = config
            self.samples.clear()
            self.alerts.clear()
            self.summary = {
                "total_samples": 0,
                "unique_processes": 0,
                "cpu_anomalies": 0,
                "memory_leak_suspicions": 0,
                "top_cpu_anomaly_processes": [],
                "top_memory_leak_processes": [],
            }
            self._stop_event.clear()
            self._running = True
            self._started_at = datetime.now(timezone.utc).isoformat()

            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=2)

        with self._lock:
            self._running = False
            self._thread = None

    def _run_loop(self) -> None:
        cfg = self._config
        sampler = ProcessSampler(top_n=cfg.top_n)
        analyzer = BehaviorAnalyzer(
            baseline_window=cfg.baseline_window,
            cpu_z_threshold=cfg.cpu_z_threshold,
            memory_window=cfg.memory_window,
            memory_leak_threshold_mb=cfg.memory_leak_threshold_mb,
        )
        logger = CsvLogger(output_path=cfg.output, dry_run=cfg.dry_run)

        sampler.prime_cpu_counters()
        logger.initialize()

        unique_pids = set()
        cpu_count: Dict[int, int] = {}
        mem_count: Dict[int, int] = {}
        names: Dict[int, str] = {}

        try:
            while not self._stop_event.is_set():
                for sample in sampler.collect():
                    result = analyzer.analyze(sample)
                    logger.write(result)

                    row = {
                        **asdict(result.sample),
                        "cpu_anomaly": result.cpu_anomaly,
                        "memory_leak_suspected": result.memory_leak_suspected,
                        "notes": result.notes,
                    }

                    with self._lock:
                        self.samples.append(row)
                        self.summary["total_samples"] += 1

                    unique_pids.add(sample.pid)
                    names[sample.pid] = sample.name

                    if result.cpu_anomaly:
                        cpu_count[sample.pid] = cpu_count.get(sample.pid, 0) + 1
                        alert = {
                            "type": "CPU",
                            "timestamp": row["timestamp"],
                            "pid": sample.pid,
                            "name": sample.name,
                            "message": result.notes,
                            "cpu_percent": sample.cpu_percent,
                            "memory_mb": sample.memory_mb,
                        }
                        with self._lock:
                            self.alerts.append(alert)
                            self.summary["cpu_anomalies"] += 1

                    if result.memory_leak_suspected:
                        mem_count[sample.pid] = mem_count.get(sample.pid, 0) + 1
                        alert = {
                            "type": "MEM",
                            "timestamp": row["timestamp"],
                            "pid": sample.pid,
                            "name": sample.name,
                            "message": result.notes,
                            "cpu_percent": sample.cpu_percent,
                            "memory_mb": sample.memory_mb,
                        }
                        with self._lock:
                            self.alerts.append(alert)
                            self.summary["memory_leak_suspicions"] += 1

                with self._lock:
                    self.summary["unique_processes"] = len(unique_pids)
                    self.summary["top_cpu_anomaly_processes"] = [
                        {
                            "pid": pid,
                            "name": names.get(pid, "<unknown>"),
                            "count": count,
                        }
                        for pid, count in sorted(cpu_count.items(), key=lambda x: x[1], reverse=True)[:5]
                    ]
                    self.summary["top_memory_leak_processes"] = [
                        {
                            "pid": pid,
                            "name": names.get(pid, "<unknown>"),
                            "count": count,
                        }
                        for pid, count in sorted(mem_count.items(), key=lambda x: x[1], reverse=True)[:5]
                    ]

                time.sleep(cfg.interval)
        finally:
            with self._lock:
                self._running = False


service = ProfilerService()
app = FastAPI(title="Process Behavior Profiler Dashboard")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"title": "Process Behavior Profiler"})


@app.get("/api/status")
def get_status() -> Dict:
    return service.status()


@app.post("/api/start")
def start_profiler(config: RunConfig) -> Dict:
    try:
        service.start(config)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "message": "Profiler started", "config": config.model_dump()}


@app.post("/api/stop")
def stop_profiler() -> Dict:
    service.stop()
    return {"ok": True, "message": "Profiler stopped"}


@app.get("/api/samples")
def get_samples(limit: int = 200) -> List[Dict]:
    limit = max(1, min(limit, 2000))
    with service._lock:
        data = list(service.samples)[-limit:]
    return data


@app.get("/api/alerts")
def get_alerts(limit: int = 200) -> List[Dict]:
    limit = max(1, min(limit, 1000))
    with service._lock:
        data = list(service.alerts)[-limit:]
    return data
