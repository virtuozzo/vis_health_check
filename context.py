from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HealthCheckContext:
    export_dir: Path
    no_compute: bool = False
    ssh_key: str = "/etc/kolla/id_rsa"
    openrc_path: str = "/etc/kolla/admin-openrc.sh"