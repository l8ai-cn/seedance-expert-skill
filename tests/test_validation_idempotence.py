from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ValidationIdempotenceTests(unittest.TestCase):
    def test_ignored_bytecode_does_not_change_validation_result(self) -> None:
        cache = ROOT / "scripts" / "__pycache__"
        cache_preexisted = cache.exists()
        cache.mkdir(exist_ok=True)
        handle = tempfile.NamedTemporaryFile(dir=cache, suffix=".pyc", delete=False)
        artifact = Path(handle.name)
        try:
            handle.write(b"not executable bytecode")
            handle.close()
            command = [sys.executable, "-B", "scripts/validate_skills.py", "--strict"]
            first = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
            second = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(first.stdout, second.stdout)
        finally:
            handle.close()
            artifact.unlink(missing_ok=True)
            if not cache_preexisted:
                try:
                    cache.rmdir()
                except OSError:
                    pass


if __name__ == "__main__":
    unittest.main()
