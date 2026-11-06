from .base import CSVExporter, JSONExporter


class AlertsExporter(CSVExporter):
    filename = "alerts.csv"
    SEVERITIES = {"error", "warning"}

    def __init__(self, vinfra, export_dir, ctx):
        super().__init__(export_dir, ctx)
        self.vinfra = vinfra

    def collect(self):
        alerts = self.vinfra.run("cluster", "alert", "list", "--long")

        header = [
            "id",
            "type",
            "datetime",
            "severity",
            "group",
            "host",
            "message",
            "node_id",
            "object_id",
        ]
        rows = []
        for alert in alerts:
            severity = alert.get("severity")

            if severity not in self.SEVERITIES:
                continue

            rows.append([
                alert.get("id", ""),
                alert.get("type", ""),
                alert.get("datetime", ""),
                severity,
                alert.get("group", ""),
                alert.get("host", ""),
                alert.get("message", ""),
                alert.get("node_id", ""),
                alert.get("object_id", ""),
            ])


        self.write(header, rows)

class ClusterOverviewExporter(JSONExporter):
    filename = "cluster_overview.json"

    def __init__(self, vinfra, export_dir, ctx=None):
        super().__init__(export_dir, ctx)
        self.vinfra = vinfra

    def collect(self):
        data = self.vinfra.run("cluster", "overview")
        self.write(data)

class HAExporter(JSONExporter):
    filename = "ha.json"

    def __init__(self, vinfra, export_dir, ctx=None):
        super().__init__(export_dir, ctx)
        self.vinfra = vinfra

    def collect(self):
        networks = self.vinfra.run("cluster", "network", "list")
        network_map = {
            n["id"]: n["name"]
            for n in networks
        }

        data = self.vinfra.run("cluster", "ha", "show")

        virtual_ips = [
            {
                "ip": vip.get("ip"),
                "network_id": vip.get("roles_set"),
                "network": network_map.get(vip.get("roles_set"), "")
            }
            for vip in (data.get("virtual_ips") or [])
        ]

        ha_export = {
            "ha_hosts": data.get("extra", {}).get("hci_hostnames", []),
            "ha_admin": data.get("ha_cluster_location", []),
            "ha_selfservice": data.get("ha_selfservice_location"),
            "virtual_ips": virtual_ips,
        }

        self.write(ha_export)
