import os
import json
import subprocess
import socket
from pathlib import Path
import xmltodict
import logging
import warnings

from cryptography.utils import CryptographyDeprecationWarning

warnings.filterwarnings(
    "ignore",
    message=r"TripleDES has been moved.*",
    category=CryptographyDeprecationWarning,
)
import paramiko

DEFAULT_SSH_KEY = "/etc/kolla/id_rsa"
DEFAULT_OPENRC_SCRIPT = "/etc/kolla/admin-openrc.sh"


def run_cmd(cmd, parsejson=False):
    logger = logging.getLogger("run_command")
    logger.debug("Running command: %s", cmd)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )
    logger.debug("stdout: %s", result.stdout.strip())
    if result.returncode != 0:
        logger.debug("stderr: %s", result.stderr.strip())
        raise RuntimeError(result.stderr.strip())

    if parsejson:
        return json.loads(result.stdout)

    return result.stdout.strip()


def run_ssh_command(host, command, timeout=10, ssh_key=DEFAULT_SSH_KEY):
    logger = logging.getLogger("run_ssh_command")
    logger.debug(f"Running on {host} ssh command: {command}")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=host,
            username="root",
            key_filename=ssh_key,
            timeout=timeout,
            banner_timeout=timeout,
            auth_timeout=timeout,
        )

        stdin, stdout, stderr = client.exec_command(
            command,
            timeout=6 * timeout,
        )

        out = stdout.read().decode()
        err = stderr.read().decode()
        exit_code = stdout.channel.recv_exit_status()
        logger.debug(f"{out}")

        return {
            "stdout": out,
            "stderr": err,
            "exit_code": exit_code,
        }

    except socket.timeout as exc:
        raise RuntimeError(
            f"SSH command timed out after {timeout}s on {host}: {command}"
        ) from exc

    finally:
        client.close()


def load_openrc(openrc_path=DEFAULT_OPENRC_SCRIPT):
    openrc_path = Path(openrc_path)

    if not openrc_path.is_file():
        raise RuntimeError(f"OpenRC file not found: {openrc_path}")

    with openrc_path.open() as f:
        for raw_line in f:
            line = raw_line.strip()

            if not line or line.startswith("#"):
                continue

            if line.startswith("export "):
                line = line[len("export "):].strip()

            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            os.environ[key] = value

    username = os.environ.get("OS_USERNAME")
    password = os.environ.get("OS_PASSWORD")

    if not username or not password:
        raise RuntimeError(
            "OpenRC must define OS_USERNAME and OS_PASSWORD"
        )

    os.environ["VINFRA_USERNAME"] = username
    os.environ["VINFRA_PASSWORD"] = password

def get_cluster_name():
    path = Path("/etc/vstorage/clusters")
    for cluster_dir in path.iterdir():
        if (cluster_dir / "auth_digest.key").is_file():
            return cluster_dir.name
    raise RuntimeError("Cluster not found")


def vstorage_stats(cluster_name):
    output = run_cmd(
        ["vstorage", "-c", cluster_name, "stat", "-X"]
    )
    return xmltodict.parse(output)["cluster"]


def vstorage_file_stats(cluster_name):
    output = run_cmd(
        ["vstorage", "-c", cluster_name, "file-stats", "/mnt/vstorage/", "-X"]
    )
    return xmltodict.parse(output)["stor-stat"]["stor-stat-entry"]