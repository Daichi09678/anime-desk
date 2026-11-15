import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from cli_process import ProcessCancelled, ProcessResult
from clone_service import CloneService


class FakeRunner:
    instances = []

    def __init__(self, cancel):
        self.cancel = cancel
        self.requests = []
        self.instances.append(self)

    def run(self, command, **kwargs):
        self.emit = kwargs["on_stdout"]
        kwargs["on_start"](self)
        self.cancel.wait(5)
        return ProcessResult(0, "", "")

    def send(self, payload):
        self.requests.append(payload)
        if not payload.get("hang"):
            self.emit(json.dumps({"chunk_file":payload["reference"]}))
            self.emit(json.dumps({"done":True}))


class CloneServiceTests(unittest.TestCase):
    def setUp(self):
        FakeRunner.instances = []
        self.service = CloneService()
        self.mock = patch("clone_service.ProcessRunner", FakeRunner)
        self.mock.start()

    def tearDown(self):
        self.service.stop()
        self.mock.stop()

    def test_reuses_process_but_passes_each_character_reference(self):
        chunks = []
        for character in ("frieren", "beatrice"):
            result = self.service.synthesize(Path.cwd(), {"reference":character}, threading.Event(), chunks.append)
            self.assertEqual(result.returncode, 0)
        self.assertEqual(len(FakeRunner.instances), 1)
        self.assertEqual([json.loads(line)["chunk_file"] for line in chunks], ["frieren", "beatrice"])

    def test_cancel_stops_process_and_next_request_restarts_cleanly(self):
        cancel = threading.Event()
        timer = threading.Timer(0.1, cancel.set)
        timer.start()
        try:
            with self.assertRaises(ProcessCancelled):
                self.service.synthesize(Path.cwd(), {"hang":True}, cancel, lambda line:None)
        finally:
            timer.join()
        self.assertIsNone(self.service.thread)
        self.service.synthesize(Path.cwd(), {"reference":"frieren"}, threading.Event(), lambda line:None)
        self.assertEqual(len(FakeRunner.instances), 2)
