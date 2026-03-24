import unittest

from profiler import BehaviorAnalyzer, ProcessSample


class BehaviorAnalyzerTest(unittest.TestCase):
    def test_cpu_anomaly_detection(self):
        analyzer = BehaviorAnalyzer(
            baseline_window=10,
            cpu_z_threshold=2.0,
            memory_window=5,
            memory_leak_threshold_mb=5.0,
        )

        for cpu in [10, 10, 10, 10, 10, 10, 10]:
            result = analyzer.analyze(
                ProcessSample(
                    timestamp="t",
                    pid=1,
                    name="proc",
                    cpu_percent=cpu,
                    memory_mb=100,
                )
            )
        self.assertFalse(result.cpu_anomaly)

        spike = analyzer.analyze(
            ProcessSample(
                timestamp="t",
                pid=1,
                name="proc",
                cpu_percent=95,
                memory_mb=100,
            )
        )
        self.assertTrue(spike.cpu_anomaly)

    def test_memory_leak_detection(self):
        analyzer = BehaviorAnalyzer(
            baseline_window=5,
            cpu_z_threshold=5.0,
            memory_window=4,
            memory_leak_threshold_mb=3.0,
        )

        for memory in [100, 104, 108, 112, 116]:
            result = analyzer.analyze(
                ProcessSample(
                    timestamp="t",
                    pid=2,
                    name="proc2",
                    cpu_percent=1,
                    memory_mb=memory,
                )
            )

        self.assertTrue(result.memory_leak_suspected)


if __name__ == "__main__":
    unittest.main()
