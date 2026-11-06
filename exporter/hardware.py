import json
import logging

from .base import CSVExporter, JSONExporter
from utils import run_ssh_command


logger = logging.getLogger(__name__)


class HardwareExporter(CSVExporter):
    filename = "hardware.csv"

    def __init__(self, hosts, export_dir, ctx):
        super().__init__(export_dir, ctx)
        self.hosts = hosts

    @staticmethod
    def get_ram_amount(dmidecode_out: str) -> str:
        total_gb = 0.0

        for line in dmidecode_out.splitlines():
            line = line.strip()

            if not line.startswith("Size:"):
                continue

            parts = line.split()
            if len(parts) < 3:
                continue

            try:
                size = float(parts[1])
            except ValueError:
                continue

            unit = parts[2].upper()

            if unit == "KB":
                size_gb = size / 1024 / 1024
            elif unit == "MB":
                size_gb = size / 1024
            elif unit == "GB":
                size_gb = size
            elif unit == "TB":
                size_gb = size * 1024
            else:
                logger.warning("Unknown RAM unit in dmidecode output: %s", unit)
                continue

            total_gb += size_gb

        return f"{int(total_gb)} GB"

    @staticmethod
    def parse_lscpu(lscpu_stdout: str) -> dict:
        result = {}

        try:
            cpu_data = json.loads(lscpu_stdout).get("lscpu", [])
        except json.JSONDecodeError as exc:
            logger.warning("Cannot parse lscpu JSON: %s", exc)
            return result

        fields = {
            "Model name:": "cpu_model",
            "CPU(s):": "cores",
            "Socket(s):": "cpu_sockets",
            "Core(s) per socket:": "cpu_cores_per_socket",
            "Thread(s) per core:": "cpu_threads_per_core",
            "NUMA node(s):": "numa_nodes",
        }

        for line in cpu_data:
            key = fields.get(line.get("field"))
            if key:
                result[key] = line.get("data")

        return result

    def collect(self):
        header = [
            "host",
            "server",
            "ram",
            "cpu_model",
            "cpu_sockets",
            "cores",
            "cpu_cores_per_socket",
            "cpu_threads_per_core",
            "numa_nodes",
        ]

        rows = []

        for host in self.hosts:
            row = {
                "host": host,
                "server": None,
                "ram": None,
                "cpu_model": None,
                "cpu_sockets": None,
                "cores": None,
                "cpu_cores_per_socket": None,
                "cpu_threads_per_core": None,
                "numa_nodes": None,
            }

            try:
                ram_info = run_ssh_command(
                    host,
                    "dmidecode -t memory | grep '^[[:space:]]*Size:' | grep -v 'No Module Installed'",
                    ssh_key=self.ctx.ssh_key,
                )
                row["ram"] = self.get_ram_amount(ram_info.get("stdout", ""))

                server_info = run_ssh_command(
                    host,
                    "dmidecode -s system-manufacturer; dmidecode -s system-product-name",
                    ssh_key=self.ctx.ssh_key,
                )
                row["server"] = " ".join(server_info.get("stdout", "").split())

                lscpu_info = run_ssh_command(
                    host,
                    "lscpu -J",
                    ssh_key=self.ctx.ssh_key,
                )
                row.update(self.parse_lscpu(lscpu_info.get("stdout", "")))

            except Exception as exc:
                logger.exception("Failed to collect hardware info from host %s", host)
                row["server"] = f"ERROR: {exc}"

            rows.append([row.get(column) for column in header])

        self.write(header, rows)


class NetworkBondExporter(CSVExporter):
    filename = "bonds.csv"

    def __init__(self, hosts, export_dir, ctx=None):
        super().__init__(export_dir, ctx)
        self.hosts = hosts

    def collect(self):
        logger.info("Collecting network bonding information")

        header = [
            "host",
            "bond",
            "mode",
            "xmit_hash_policy",
            "mii_status",
            "slaves",
        ]

        rows = []

        for host in self.hosts:
            try:
                result = run_ssh_command(
                    host,
                    "ls /proc/net/bonding",
                    ssh_key=self.ctx.ssh_key,
                )

                bonds = result.get("stdout", "").split()

                for bond_iface in bonds:
                    data = run_ssh_command(
                        host,
                        f"cat /proc/net/bonding/{bond_iface}",
                        ssh_key=self.ctx.ssh_key,
                    ).get("stdout", "")

                    bond = {
                        "mode": "",
                        "xmit_hash_policy": "",
                        "mii_status": "",
                        "slaves": [],
                    }

                    for line in data.splitlines():
                        line = line.strip()

                        if not line:
                            continue

                        if line.startswith("Bonding Mode:"):
                            bond["mode"] = line.split(":", 1)[1].strip()

                        elif line.startswith("Transmit Hash Policy:"):
                            bond["xmit_hash_policy"] = (
                                line.split(":", 1)[1].strip()
                            )

                        elif line.startswith("MII Status:"):
                            # First MII Status belongs to the bond itself.
                            if not bond["mii_status"]:
                                bond["mii_status"] = (
                                    line.split(":", 1)[1].strip()
                                )

                        elif line.startswith("Slave Interface:"):
                            slave = line.split(":", 1)[1].strip()
                            bond["slaves"].append(slave)

                    rows.append([
                        host,
                        bond_iface,
                        bond["mode"],
                        bond["xmit_hash_policy"],
                        bond["mii_status"],
                        " ".join(bond["slaves"]),
                    ])

            except Exception as exc:
                logger.exception(
                    "Failed to collect bonding info from host %s",
                    host,
                )

                rows.append([host,"","","","ERROR",str(exc),])

        self.write(header, rows)

class EthernetsExporter(CSVExporter):
    filename = "ethernets.csv"

    def __init__(self, hosts, export_dir, ctx=None):
        super().__init__(export_dir, ctx)
        self.hosts = hosts

    def collect(self):
        logger.info("Collecting Ethernet interface information")

        header = [
            "host",
            "name",
            "product",
            "businfo",
            "driver",
        ]

        rows = []

        for host in self.hosts:
            try:
                result = run_ssh_command(
                    host,
                    "lshw -c network -json -numeric", timeout=30,
                    ssh_key=self.ctx.ssh_key,
                )

                stdout = result.get("stdout", "").strip()

                if not stdout:
                    logger.warning("Empty lshw output on host %s", host,)
                    continue

                ethernets = json.loads(stdout)

                if not isinstance(ethernets, list):
                    ethernets = [ethernets]

                for elem in ethernets:
                    logical_name = elem.get("logicalname") or ""

                    if isinstance(logical_name, list):
                        logical_name = " ".join(logical_name)

                    configuration = elem.get("configuration") or {}

                    rows.append([
                        host,
                        logical_name,
                        elem.get("product") or "",
                        elem.get("businfo") or "",
                        configuration.get("driver") or "",
                    ])

            except json.JSONDecodeError as exc:
                logger.error("Cannot parse lshw JSON on host %s: %s",host,exc,)

                rows.append([host,"","","",f"ERROR: invalid lshw JSON: {exc}",])

            except Exception as exc:
                logger.exception("Failed to collect Ethernet information from host %s",host,)

                rows.append([host,"","","",f"ERROR: {exc}",])

        self.write(header, rows)



class StorageHardwareExporter(JSONExporter):
    filename = "storage_hardware.json"

    def __init__(self, hosts, export_dir, ctx=None):
        super().__init__(export_dir, ctx)
        self.hosts = hosts

    def collect(self):
        logger.info("Collecting storage hardware information")

        data = []

        for host in self.hosts:
            try:
                result = run_ssh_command(
                    host,
                    "lshw -class storage -json -numeric",
                    ssh_key=self.ctx.ssh_key,
                )

                stdout = result.get("stdout", "").strip()

                if not stdout:
                    data.append({
                        "host": host,
                        "storage": [],
                        "error": "Empty lshw output",
                    })
                    continue

                storage = json.loads(stdout)

                data.append({"host": host,"storage": storage,})

            except json.JSONDecodeError as exc:
                logger.exception("Cannot parse storage lshw JSON on host %s",host,)

                data.append({"host": host,"storage": [],"error": f"Invalid lshw JSON: {exc}",})

            except Exception as exc:
                logger.exception("Failed to collect storage information from host %s",host,)

                data.append({"host": host,"storage": [],"error": str(exc),})

        self.write(data)