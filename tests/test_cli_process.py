from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest

from cli_process import ProcessCancelled, ProcessRunner


class ProcessRunnerTests(unittest.TestCase):
    def run_python(self, source, **kwargs):
        runner = ProcessRunner(kwargs.pop("cancel", None))
        return runner, runner.run([sys.executable, "-u", "-c", source], cwd=Path.cwd(), **kwargs)

    def test_drains_large_stderr_while_stdout_streams_and_caps_retained_output(self):
        runner, result = self.run_python("import sys; sys.stderr.write('diagnostic\\n' * 60000); sys.stderr.flush(); print('DONE')", timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertIn("DONE", result.stdout)
        self.assertLessEqual(len(result.stderr), runner.OUTPUT_LIMIT)
        self.assertTrue(runner.proc.stdout.closed)

    def test_timeout_applies_before_stdout_eof(self):
        runner = ProcessRunner()
        start = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            runner.run([sys.executable, "-c", "import time; time.sleep(60)"], cwd=Path.cwd(), timeout=0.3)
        self.assertLess(time.monotonic() - start, 4)
        self.assertIsNotNone(runner.proc.poll())

    def test_cancel_stops_running_process(self):
        cancel = threading.Event()
        timer = threading.Timer(0.3, cancel.set)
        runner = ProcessRunner(cancel)
        timer.start()
        try:
            with self.assertRaises(ProcessCancelled):
                runner.run([sys.executable, "-c", "import time; time.sleep(60)"], cwd=Path.cwd(), timeout=10)
            self.assertIsNotNone(runner.proc.poll())
        finally:
            timer.cancel()

    def test_timeout_still_works_when_cli_does_not_read_large_input(self):
        runner = ProcessRunner()
        start = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            runner.run([sys.executable, "-c", "import time; time.sleep(60)"], cwd=Path.cwd(), timeout=0.3,
                       interactive=True, on_start=lambda r: r.send({"text": "x" * 2000000}))
        self.assertLess(time.monotonic() - start, 4)

    def test_utf8_split_across_pipe_chunks(self):
        source = "import os,sys; text='Halo, Frieren 🌸'.encode(); [os.write(sys.stdout.fileno(), bytes([b])) for b in text]"
        _, result = self.run_python(source, timeout=5)
        self.assertEqual(result.stdout.strip(), "Halo, Frieren 🌸")

    def test_callback_completion_terminates_server_and_owned_children(self):
        runner = ProcessRunner()
        child_pids = []

        def handle(line):
            child_pids.append(int(line))
            return True

        source = "import subprocess,sys,time; child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); print(child.pid,flush=True); time.sleep(60)"
        runner.run([sys.executable, "-u", "-c", source], cwd=Path.cwd(), timeout=5, on_stdout=handle)
        if sys.platform == "win32":
            import ctypes
            kernel = ctypes.WinDLL("kernel32")
            kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
            kernel.OpenProcess.restype = ctypes.c_void_p
            kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            handle = kernel.OpenProcess(0x100000, False, child_pids[0])
            if handle:
                try:
                    self.assertEqual(kernel.WaitForSingleObject(handle, 1000), 0)
                finally:
                    kernel.CloseHandle(handle)


if __name__ == "__main__":
    unittest.main()
