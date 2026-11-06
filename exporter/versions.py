from .base import CSVExporter
from utils import run_ssh_command


class VersionsExporter(CSVExporter):
#Content of /etc/hci-release is not actual in recent releases
    filename = "versions.csv"

    def __init__(self, hosts, export_dir, ctx):
        super().__init__(export_dir, ctx)
        self.hosts = hosts

    def collect(self):
        headers = ["host", "version"]
        rows = []
        product_names = [
            "Virtuozzo Hybrid Infrastructure",
            "Virtuozzo Infrastructure",
        ]
        for host in self.hosts:
            result = run_ssh_command(
                host=host,
                command="cat /etc/hci-release",
                ssh_key=self.ctx.ssh_key
            )

            if result["exit_code"] == 0:
                output = result["stdout"].strip()
                version = output.strip()
                for product_name in product_names:
                    if version.startswith(product_name):
                        version = version[len(product_name):].strip()
                        break

            rows.append([host, version])

        self.write(headers, rows)

