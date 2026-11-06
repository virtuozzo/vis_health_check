from .base import CSVExporter, TextExporter
from utils import run_ssh_command, run_cmd
import logging
import json

logger = logging.getLogger(__name__)
class DisksExporter:
    """
    Exports:
      - all_disks.csv
      - cses.csv
      - caches.csv
    """

    def __init__(self, vinfra, nodes, export_dir,ctx):
        self.vinfra = vinfra
        self.nodes = nodes
        self.export_dir = export_dir
        self.ctx = ctx
        self.node_map = {
            n["id"]: n["host"]
            for n in self.nodes
        }
    def collect(self):
        disks = self.vinfra.run(
            "node",
            "disk",
            "list",
            "-a",
            "--long"
        )


        self._export_all_disks(disks)
        self._export_cses(disks)
        self._export_caches(disks)
        self._export_md(disks)


    # -------------------------------------------------

    def _export_all_disks(self, disks):
        exporter = CSVExporter(self.export_dir)
        exporter.filename = "all_disks.csv"

        headers = ['server', 'device', 'type', 'role', 'model', 'size']
        rows = []

        for d in disks:
            host = self.node_map.get(d.get("node_id"), d.get("node_id"))
            rows.append([
                host,
                d.get("device"),
                d.get("type"),
                d.get("role"),
                d.get("model"),
                int(d.get("physical_size") / 1073741824),
            ])

        exporter.write(headers, rows)

    # -------------------------------------------------

    def _export_cses(self, disks):
        exporter = CSVExporter(self.export_dir)
        exporter.filename = "cses.csv"

        headers = ['server', 'cs_ids', 'device', 'type', 'tier', 'journal', 'encryption', 'model']
        rows = []

        for d in disks:
            if d.get("role") == "cs" and d.get("chunk_servers"):
                cs = d["chunk_servers"][0]
                host = self.node_map.get(d.get("node_id"), d.get("node_id"))

                rows.append([
                    host,
                    ' '.join([str(c) for c in d.get("service_id", [])]),
                    d.get("device"),
                    d.get("type"),
                    cs.get("tier"),
                    cs.get("journal_type"),
                    cs.get("encryption"),
                    d.get("model"),
                ])

        exporter.write(headers, rows)

    # -------------------------------------------------

    def _export_caches(self, disks):
        exporter = CSVExporter(self.export_dir)
        exporter.filename = "caches.csv"

        headers = ['server', 'device', 'type', 'tier', 'model']
        rows = []

        for d in disks:
            role = d.get("role", "")

            if role.endswith("journal") and d.get("cache"):
                host = self.node_map.get(d.get("node_id"), d.get("node_id"))

                rows.append([
                    host,
                    d.get("device"),
                    d.get("type"),
                    d["cache"].get("journal_tier"),
                    d.get("model"),
                ])

        exporter.write(headers, rows)

    def _export_md(self, disks):
        exporter = CSVExporter(self.export_dir)
        exporter.filename = "md.csv"

        def human_size(size):
            try:
                size = int(size)
            except (TypeError, ValueError):
                return ""

            units = ["B", "K", "M", "G", "T", "P"]
            value = float(size)

            for unit in units:
                if value < 1024 or unit == units[-1]:
                    if unit == "B":
                        return f"{int(value)}B"
                    return f"{value:.1f}{unit}"

                value /= 1024

            return str(size)

        def find_physical_disk(devname, devices):
            current = devname

            while current:
                dev = devices.get(current)

                if not dev:
                    return None

                if dev.get("type") == "disk":
                    return dev

                current = dev.get("pkname")

            return None

        def get_md_members(host):
            members = set()

            try:
                result = run_ssh_command(
                    host,
                    "cat /proc/mdstat",
                    ssh_key=self.ctx.ssh_key,
                )

                if result.get("exit_code") != 0:
                    raise RuntimeError(
                        result.get("stderr", "").strip()
                        or "Failed to read /proc/mdstat"
                    )

                output = result.get("stdout", "")

                for line in output.splitlines():
                    line = line.strip()

                    if not line.startswith("md") or " : " not in line:
                        continue

                    parts = line.split()

                    try:
                        active_idx = parts.index("active")
                    except ValueError:
                        continue

                    # Example:
                    # md127 : active raid1 sda1[0] sdb1[1]
                    for token in parts[active_idx + 2:]:
                        if "[" not in token:
                            continue

                        dev = token.split("[", 1)[0]
                        dev = dev.split("(", 1)[0]

                        if dev:
                            members.add(dev)

            except Exception:
                logger.exception(
                    "Failed to get /proc/mdstat information from host %s",
                    host,
                )

            return members

        def get_lsblk(host):
            try:
                result = run_ssh_command(
                    host,
                    "lsblk -J -b -o NAME,KNAME,TYPE,SIZE,MODEL,PKNAME", timeout= 30,
                    ssh_key=self.ctx.ssh_key,
                )

                if result.get("exit_code") != 0:
                    raise RuntimeError(
                        result.get("stderr", "").strip()
                        or "lsblk failed"
                    )

                data = json.loads(
                    result.get("stdout", "")
                )

            except Exception:
                logger.exception(
                    "Failed to execute lsblk on host %s",
                    host,
                )
                return {}

            devices = {}

            def walk(items):
                for item in items:
                    kname = item.get("kname")

                    if kname:
                        devices[kname] = item

                    if item.get("children"):
                        walk(item["children"])

            walk(data.get("blockdevices", []))

            return devices

        headers = [
            "server",
            "device",
            "size",
            "model",
        ]

        rows = []

        md_nodes = set()

        for disk in disks:
            device = disk.get("device") or ""

            if device.startswith("md"):
                node_id = disk.get("node_id")
                if node_id:
                    md_nodes.add(node_id)

        md_hosts = [
            self.node_map[node_id]
            for node_id in md_nodes
            if node_id in self.node_map
        ]

        logger.debug(
            "MD hosts: %s",
            " ".join(md_hosts),
        )

        for host in md_hosts:
            devices = get_lsblk(host)

            if not devices:
                continue

            members = get_md_members(host)

            logger.debug(
                "MD members on %s: %s",
                host,
                " ".join(sorted(members)),
            )

            physical_disks = {}

            for member in members:
                disk = find_physical_disk(
                    member,
                    devices,
                )

                if disk:
                    physical_disks[disk["kname"]] = disk

            for name in sorted(physical_disks):
                disk = physical_disks[name]

                rows.append([
                    host,
                    f"/dev/{disk['kname']}",
                    human_size(disk.get("size")),
                    (disk.get("model") or "").strip(),
                ])

        exporter.write(headers, rows)
class ExternalStorageExporter(CSVExporter):
    filename = "external_storage.csv"

    def __init__(self, vinfra, export_dir,ctx):
        super().__init__(export_dir,ctx)
        self.vinfra = vinfra

    def collect(self):
        header = ['name', 'driver', 'enabled', 'configured', 'status']
        storage_list = self.vinfra.run("service", "compute", "storage", "list")
        rows = []
        for stor in storage_list:
            rows.append([stor.get('name'),
                         stor.get('params').get('volume_driver'),
                         stor.get('enabled'),
                         stor.get('configured'),
                         stor.get('status')])

        self.write(header, rows)

class VstorageGetEvent(TextExporter):
    filename = "vstorage_get-event.txt"

    def __init__(self, cluster_name, export_dir, ctx=None):
        super().__init__(export_dir, ctx)
        self.cluster_name = cluster_name

    def collect(self):
        lines = run_cmd(["vstorage", "-c", self.cluster_name, "get-event"])
        self.write(lines)
#        self.write("\n".join(lines) + "\n")

class VstorageStat(TextExporter):
    filename = "vstorage_stat.txt"

    def __init__(self, cluster_name, export_dir, ctx=None):
        super().__init__(export_dir, ctx)
        self.cluster_name = cluster_name

    def collect(self):
        lines = run_cmd(["vstorage", "-c", self.cluster_name, "stat", "-n"])
        self.write(lines)

class VstorageConfig(TextExporter):
    filename = "vstorage_config.txt"

    def __init__(self, cluster_name, export_dir, ctx=None):
        super().__init__(export_dir, ctx)
        self.cluster_name = cluster_name

    def collect(self):
        lines = run_cmd(["vstorage", "-c", self.cluster_name, "get-config"])
        self.write(lines)
