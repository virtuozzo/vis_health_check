from .base import CSVExporter
from datetime import datetime



class LicenseExporter(CSVExporter):
    """
    Exports license information exactly as original script,
    converting expiration_ts to readable date.
    """
    filename = "license.csv"

    def __init__(self, vinfra, export_dir ,ctx):
        super().__init__(export_dir,ctx)
        self.vinfra = vinfra

    def collect(self):
        license_data = self.vinfra.run("cluster", "license", "show")

        headers = [
            "capacity",
            "core_number",
            "core_number_used",
            "expiration",
            "keynumber",
            "license_type",
            "status",
            "used_size"
        ]

        expiration = ""
        expiration_ts = license_data.get("expiration_ts")

        if expiration_ts:
            try:
                expiration = datetime.utcfromtimestamp(
                    int(expiration_ts)
                ).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                expiration = str(expiration_ts)

        row = [[
            license_data.get("capacity"),
            license_data.get("core_number"),
            license_data.get("core_number_used"),
            expiration,
            license_data.get("keynumber"),
            license_data.get("license_type"),
            license_data.get("status"),
            license_data.get("used_size"),
        ]]

        self.write(headers, row)