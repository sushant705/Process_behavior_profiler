#!/usr/bin/env python3
"""Process Behavior Profiler.

Cross-platform process profiler (Windows/Linux/macOS) powered by psutil.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Deque, Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class ProcessSample:
    timestamp: str
    pid: int
    name: str
    cpu_percent: float
    memory_mb: float


@dataclass(frozen=True)
class AnalysisResult:
    sample: ProcessSample
    cpu_anomaly: bool
    memory_leak_suspected: bool
    notes: str


class ProcessSampler:
    def __init__(self, top_n: int) -> None:
        import psutil

        self.psutil = psutil
        self.top_n = top_n

    def prime_cpu_counters(self) -> None:
        for proc in self.psutil.process_iter(attrs=[]):
            try:
                proc.cpu_percent(interval=None)
            except (
                self.psutil.NoSuchProcess,
                self.psutil.AccessDenied,
                self.psutil.ZombieProcess,
            ):
                continue

    def collect(self) -> List[ProcessSample]:
        rows: List[Tuple[int, str, float, float]] = []
        now = datetime.now(timezone.utc).isoformat()

        for proc in self.psutil.process_iter(attrs=["pid", "name"]):
            try:
                pid = proc.pid
                name = proc.info.get("name") or "<unknown>"
                cpu_percent = proc.cpu_percent(interval=None)
                memory_mb = proc.memory_info().rss / (1024 * 1024)
                rows.append((pid, name, cpu_percent, memory_mb))
            except (
                self.psutil.NoSuchProcess,
                self.psutil.AccessDenied,
                self.psutil.ZombieProcess,
            ):
                continue

        rows.sort(key=lambda x: x[2], reverse=True)
        selected = rows[: self.top_n]

        return [
            ProcessSample(
                timestamp=now,
                pid=pid,
                name=name,
                cpu_percent=cpu,
                memory_mb=mem,
            )
            for pid, name, cpu, mem in selected
        ]


class BehaviorAnalyzer:
    def __init__(
        self,
        baseline_window: int,
        cpu_z_threshold: float,
        memory_window: int,
        memory_leak_threshold_mb: float,
    ) -> None:
        self.baseline_window = baseline_window
        self.cpu_z_threshold = cpu_z_threshold
        self.memory_window = memory_window
        self.memory_leak_threshold_mb = memory_leak_threshold_mb

        self.cpu_history: Dict[int, Deque[float]] = defaultdict(
            lambda: deque(maxlen=baseline_window)
        )
        self.memory_history: Dict[int, Deque[float]] = defaultdict(
            lambda: deque(maxlen=max(memory_window, baseline_window))
        )

    def _cpu_anomaly(self, pid: int, cpu_value: float) -> Tuple[bool, str]:
        history = self.cpu_history[pid]
        if len(history) < 3:
            return False, ""

        mean = statistics.fmean(history)
        stdev = statistics.pstdev(history)

        if stdev == 0:
            if mean > 0 and cpu_value >= mean * (1 + self.cpu_z_threshold):
                return (
                    True,
                    f"cpu_jump_from_flat_mean={mean:.2f} to {cpu_value:.2f}, threshold_multiplier={1 + self.cpu_z_threshold:.2f}",
                )
            return False, ""

        z = (cpu_value - mean) / stdev
        if z >= self.cpu_z_threshold:
            return (
                True,
                f"cpu_z={z:.2f}, mean={mean:.2f}, stdev={stdev:.2f}, threshold={self.cpu_z_threshold:.2f}",
            )
        return False, ""

    def _memory_leak(self, pid: int) -> Tuple[bool, str]:
        history = self.memory_history[pid]
        if len(history) < self.memory_window:
            return False, ""

        window = list(history)[-self.memory_window :]
        deltas = [window[i + 1] - window[i] for i in range(len(window) - 1)]
        avg_growth = statistics.fmean(deltas)

        if avg_growth >= self.memory_leak_threshold_mb:
            return (
                True,
                f"mem_growth={avg_growth:.2f}MB/sample over {self.memory_window} samples, threshold={self.memory_leak_threshold_mb:.2f}",
            )
        return False, ""

    def analyze(self, sample: ProcessSample) -> AnalysisResult:
        cpu_flag, cpu_note = self._cpu_anomaly(sample.pid, sample.cpu_percent)

        self.cpu_history[sample.pid].append(sample.cpu_percent)
        self.memory_history[sample.pid].append(sample.memory_mb)

        mem_flag, mem_note = self._memory_leak(sample.pid)
        notes = "; ".join(n for n in [cpu_note, mem_note] if n)

        return AnalysisResult(
            sample=sample,
            cpu_anomaly=cpu_flag,
            memory_leak_suspected=mem_flag,
            notes=notes,
        )


class CsvLogger:
    HEADER = [
        "timestamp",
        "pid",
        "name",
        "cpu_percent",
        "memory_mb",
        "cpu_anomaly",
        "memory_leak_suspected",
        "notes",
    ]

    def __init__(self, output_path: str, dry_run: bool) -> None:
        self.output_path = output_path
        self.dry_run = dry_run

    def initialize(self) -> None:
        if self.dry_run:
            return
        with open(self.output_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(self.HEADER)

    def write(self, result: AnalysisResult) -> None:
        if self.dry_run:
            return
        with open(self.output_path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                [
                    result.sample.timestamp,
                    result.sample.pid,
                    result.sample.name,
                    f"{result.sample.cpu_percent:.2f}",
                    f"{result.sample.memory_mb:.2f}",
                    result.cpu_anomaly,
                    result.memory_leak_suspected,
                    result.notes,
                ]
            )


class ProfilerRunner:
    def __init__(
        self,
        sampler: ProcessSampler,
        analyzer: BehaviorAnalyzer,
        logger: CsvLogger,
        interval: float,
        duration: float,
    ) -> None:
        self.sampler = sampler
        self.analyzer = analyzer
        self.logger = logger
        self.interval = interval
        self.duration = duration

    def run(self) -> None:
        self.sampler.prime_cpu_counters()
        self.logger.initialize()

        end_time = time.monotonic() + self.duration
        total = 0
        pids_seen = set()
        cpu_alerts: Counter[int] = Counter()
        mem_alerts: Counter[int] = Counter()
        names: Dict[int, str] = {}

        while time.monotonic() < end_time:
            for sample in self.sampler.collect():
                result = self.analyzer.analyze(sample)
                self.logger.write(result)

                total += 1
                pids_seen.add(sample.pid)
                names[sample.pid] = sample.name

                if result.cpu_anomaly:
                    cpu_alerts[sample.pid] += 1
                    print(
                        f"[ALERT][CPU] pid={sample.pid} name={sample.name} cpu={sample.cpu_percent:.2f}% {result.notes}"
                    )

                if result.memory_leak_suspected:
                    mem_alerts[sample.pid] += 1
                    print(
                        f"[ALERT][MEM] pid={sample.pid} name={sample.name} mem={sample.memory_mb:.2f}MB {result.notes}"
                    )

            time.sleep(self.interval)

        self._print_summary(total, pids_seen, cpu_alerts, mem_alerts, names)

    def _print_summary(
        self,
        total: int,
        pids_seen: set[int],
        cpu_alerts: Counter[int],
        mem_alerts: Counter[int],
        names: Dict[int, str],
    ) -> None:
        print("\n=== Process Behavior Profiler Summary ===")
        print(f"Total samples: {total}")
        print(f"Unique processes observed: {len(pids_seen)}")
        print(f"CPU anomalies: {sum(cpu_alerts.values())}")
        print(f"Memory leak suspicions: {sum(mem_alerts.values())}")

        print("\nTop CPU anomaly processes:")
        for pid, count in cpu_alerts.most_common(5):
            print(f"  pid={pid} name={names.get(pid, '<unknown>')} count={count}")
        if not cpu_alerts:
            print("  none")

        print("\nTop memory leak suspected processes:")
        for pid, count in mem_alerts.most_common(5):
            print(f"  pid={pid} name={names.get(pid, '<unknown>')} count={count}")
        if not mem_alerts:
            print("  none")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process Behavior Profiler")
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--baseline-window", type=int, default=10)
    parser.add_argument("--cpu-z-threshold", type=float, default=3.0)
    parser.add_argument("--memory-window", type=int, default=6)
    parser.add_argument("--memory-leak-threshold-mb", type=float, default=2.0)
    parser.add_argument("--output", type=str, default="process_metrics.csv")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runner = ProfilerRunner(
        sampler=ProcessSampler(top_n=args.top_n),
        analyzer=BehaviorAnalyzer(
            baseline_window=args.baseline_window,
            cpu_z_threshold=args.cpu_z_threshold,
            memory_window=args.memory_window,
            memory_leak_threshold_mb=args.memory_leak_threshold_mb,
        ),
        logger=CsvLogger(output_path=args.output, dry_run=args.dry_run),
        interval=args.interval,
        duration=args.duration,
    )
    runner.run()


if __name__ == "__main__":
    main()
