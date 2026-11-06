from .base import CSVExporter, JSONExporter


class ComputeNetworksExporter(CSVExporter):

    filename = "compute_networks.csv"

    def __init__(self, vinfra, export_dir,ctx):
        super().__init__(export_dir,ctx)
        self.vinfra = vinfra

    def collect(self):
        networks = self.vinfra.run(
            "service",
            "compute",
            "network",
            "list",
            "--type",
            "physical",
            "--long"
        )

        headers = [
            "name",
            "physical_network",
            "CIDR",
            "gateway",
            "VLAN",
            "MTU"
        ]

        rows = []
        for net in networks:
            rows.append([
                net.get("name"),
                net.get("physical_network"),
                net.get("cidr"),
                net.get("gateway_ip"),
                net.get("vlan_id"),
                net.get("mtu"),
            ])

        self.write(headers, rows)


class ComputeNodeExporter(CSVExporter):

    filename = "compute_nodes.csv"

    def __init__(self, vinfra, export_dir,ctx):
        super().__init__(export_dir,ctx)
        self.vinfra = vinfra

    def collect(self):
        nodes = self.vinfra.run(
            "service",
            "compute",
            "node",
            "list",
            "--long"
        )
        headers = ["host", "cpu_model", "in_maintenance", "state", "roles" ]
        rows = []
        for node in nodes:
            roles = node.get("roles")
            roles.sort()
            rows.append([
                node.get("host"),
                node.get("cpu_model", ""),
                node.get("in_maintenance"),
                node.get("state"),
                ' '.join(roles)
            ])
        self.write(headers, rows)

class ComputeStoragePoliciesExporter(CSVExporter):
    filename = "compute_storage_policies.csv"

    FAILURE_DOMAINS = {
        0: "disk",
        1: "host",
        2: "row",
        3: "rack",
    }

    EMPTY_QOS = {
        "read_bytes_sec": -1,
        "read_bytes_sec_per_gb": -1,
        "read_bytes_sec_per_gb_min": -1,
        "read_iops_sec": -1,
        "read_iops_sec_per_gb": -1,
        "read_iops_sec_per_gb_min": -1,
        "total_bytes_sec": -1,
        "total_bytes_sec_per_gb": -1,
        "total_bytes_sec_per_gb_min": -1,
        "total_iops_sec": -1,
        "total_iops_sec_per_gb": -1,
        "total_iops_sec_per_gb_min": -1,
        "write_bytes_sec": -1,
        "write_bytes_sec_per_gb": -1,
        "write_bytes_sec_per_gb_min": -1,
        "write_iops_sec": -1,
        "write_iops_sec_per_gb": -1,
        "write_iops_sec_per_gb_min": -1,
    }

    def __init__(self, vinfra, export_dir, ctx=None):
        super().__init__(export_dir, ctx)
        self.vinfra = vinfra

    @staticmethod
    def get_redundancy(redundancy):
        if not redundancy:
            return ""

        params = redundancy.get("params") or {}
        redundancy_type = redundancy.get("type")

        if redundancy_type == "replicas":
            return f"replicas={params.get('norm', '')}"

        if redundancy_type == "encoding":
            return f"encoding={params.get('M', '')}+{params.get('N', '')}"

        return redundancy_type or ""

    @classmethod
    def get_failure_domain(cls, value):
        if isinstance(value, int):
            return cls.FAILURE_DOMAINS.get(value, f"unknown({value})")

        if isinstance(value, str):
            return value

        return ""

    @classmethod
    def qos_is_set(cls, qos):
        if not qos:
            return False

        return qos != cls.EMPTY_QOS

    def collect(self):
        policies = self.vinfra.run(
            "service",
            "compute",
            "storage-policy",
            "list",
            "--long",
        )

        headers = [
            "name",
            "available",
            "qos_set",
            "redundancy",
            "storage",
            "tier",
            "failure_domain",
        ]

        rows = []

        for policy in policies:
            rows.append([
                policy.get("name"),
                policy.get("available"),
                self.qos_is_set(policy.get("qos")),
                self.get_redundancy(policy.get("redundancy")),
                policy.get("storage"),
                policy.get("tier"),
                self.get_failure_domain(policy.get("failure_domain")),
            ])

        self.write(headers, rows)

class ComputeShowExporter(JSONExporter):
    filename = "compute_show.json"

    def __init__(self, vinfra, export_dir, ctx=None):
        super().__init__(export_dir, ctx)
        self.vinfra = vinfra

    def collect(self):
        data = self.vinfra.run("service", "compute", "show")
        self.write(data)


class ComputeStatExporter(JSONExporter):
    filename = "compute_stat.json"

    def __init__(self, vinfra, export_dir, ctx=None):
        super().__init__(export_dir, ctx)
        self.vinfra = vinfra

    def collect(self):
        data = self.vinfra.run("service", "compute", "stat")
        self.write(data)
