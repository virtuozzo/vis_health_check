import json
import shutil
import subprocess
import logging

class VinfraError(RuntimeError):
    pass


class Vinfra:

    def __init__(self, vinfra_bin="vinfra", timeout=600):
        if not shutil.which(vinfra_bin):
            raise VinfraError("vinfra binary not found")
        self.vinfra_bin = vinfra_bin
        self.timeout = timeout
        self.logger = logging.getLogger(self.__class__.__name__)

    def run(self, *args):
        cmd = [self.vinfra_bin, *args, "-f", "json"]
        self.logger.debug("Running vinfra command: %s", " ".join(cmd))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout
        )
        self.logger.debug(f"Result {result.stdout}")
        if result.returncode != 0:
            self.logger.debug("vinfra stderr: %s", result.stderr.strip())
            raise VinfraError(result.stderr.strip())

        return json.loads(result.stdout)