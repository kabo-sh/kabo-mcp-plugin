"""Exercise the shipped CLI across independent processes, without a host or network."""
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = [ROOT / "skills" / name / "scripts/creator_library.py" for name in
           ("start-with-kabo", "pick-daily-viral-videos", "review-new-posts")]
LOAD = """
import importlib.util, sys, time
spec = importlib.util.spec_from_file_location('library', sys.argv[1])
lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)
"""
RUN = LOAD + """
# Widen the valid interleaving after reading state, so a missing operation lock loses updates.
read = lib.read_picks
def slow_read(directory):
    value = read(directory)
    time.sleep(0.1)
    return value
lib.read_picks = slow_read
print('ready', flush=True)
sys.stdin.readline()
sys.argv = sys.argv[1:]
lib.main()
"""


class LibraryConcurrency(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kabo-library-concurrency-")
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.library = self.root / "library"
        self.result = self.root / "result.json"
        self.result.write_text(json.dumps({"status": "ready", "windows": {}}))

    def cli(self, *args, source=SCRIPTS[0]):
        return subprocess.run([sys.executable, "-I", "-B", str(source), *map(str, args)],
                              capture_output=True, text=True, timeout=10)

    def concurrent_picks(self, dates):
        workers = []
        try:
            for i, day in enumerate(dates):
                command = [sys.executable, "-I", "-B", "-c", RUN, str(SCRIPTS[i % len(SCRIPTS)]),
                           "for-you", "--library", str(self.library), "--result", str(self.result),
                           "--date", day, "--write"]
                workers.append(subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                                stderr=subprocess.PIPE, text=True))
            for worker in workers:
                self.assertEqual(worker.stdout.readline().strip(), "ready")
            for worker in workers:
                worker.stdin.write("go\n")
                worker.stdin.flush()
            outputs = []
            for worker in workers:
                stdout, stderr = worker.communicate(timeout=15)
                self.assertEqual(worker.returncode, 0, stderr)
                outputs.append(json.loads(stdout))
            return outputs
        finally:
            for worker in workers:
                if worker.poll() is None:
                    worker.kill()
                worker.communicate()

    def test_different_days_survive_overlapping_writes_from_all_three_skills(self):
        days = [f"2026-11-{day:02d}" for day in range(10, 16)]
        self.concurrent_picks(days)
        saved = json.loads((self.library / "picks.json").read_text())
        self.assertEqual(set(saved["days"]), set(days))

    def test_same_day_is_recorded_once_and_the_other_hosts_reuse_it(self):
        results = self.concurrent_picks(["2026-11-16"] * 6)
        self.assertEqual(sum(item.get("recorded", False) for item in results), 1)
        self.assertEqual(sum(item.get("already_recorded", False) for item in results), 5)
        self.assertTrue(all(item["picks"] == results[0]["picks"] for item in results))

    def test_other_accounts_progress_and_a_killed_owner_releases_its_lock(self):
        holder = subprocess.Popen([sys.executable, "-I", "-B", "-c", LOAD + """
with lib.library_lock(sys.argv[2]):
    print('locked', flush=True)
    sys.stdin.read()
""", str(SCRIPTS[0]), str(self.library)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(holder.stdout.readline().strip(), "locked")
            other = self.cli("picks", "--library", self.root / "other")
            self.assertEqual(other.returncode, 0, other.stderr)
        finally:
            holder.kill()
            holder.communicate(timeout=5)
        retry = self.cli("picks", "--library", self.library, source=SCRIPTS[2])
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertFalse(json.loads(retry.stdout)["checked"])

    def test_failed_command_releases_the_library(self):
        self.result.write_text("invalid json")
        failed = self.cli("for-you", "--library", self.library, "--result", self.result, "--write")
        self.assertNotEqual(failed.returncode, 0)
        retry = self.cli("picks", "--library", self.library, source=SCRIPTS[1])
        self.assertEqual(retry.returncode, 0, retry.stderr)

    def test_failed_replace_keeps_the_previous_json_and_cleans_its_temp_file(self):
        spec = importlib.util.spec_from_file_location("library", SCRIPTS[0])
        lib = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lib)
        target = self.root / "state.json"
        target.write_text('{"previous": true}\n')
        with patch.object(lib.os, "replace", side_effect=OSError("simulated replacement failure")):
            with self.assertRaises(OSError):
                lib.write_json(target, {"replacement": True})
        self.assertEqual(json.loads(target.read_text()), {"previous": True})
        self.assertEqual(list(self.root.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
