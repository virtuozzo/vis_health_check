from .framework import BaseCheck, CheckResult
import json
from utils import run_ssh_command, run_cmd
import configparser
from pathlib import Path
from urllib.parse import unquote
import urllib.request


class ComputeParamsCheck(BaseCheck):
    name = "compute_params"

    def __init__(self, vinfra, ctx=None):
        super().__init__(ctx)
        self.vinfra = vinfra

    def run(self):
        self.logger.info("Checking compute Parameters")

        result = []
        compute_thresholds = {'ram_allocation_ratio': 1.0, 'cpu_allocation_ratio': 8.0}
        try:
            compute = self.vinfra.run("service", "compute", "show")
            params = compute.get("options").get("custom_params")
            if params:
                for param in params:
                    if param.get("property") in compute_thresholds.keys():
                        if param.get("value") > compute_thresholds[param.get("property")]:
                                result.append({param.get("property"): param.get("value")})


        except Exception as e:
            return CheckResult(self.name, "ERROR", [str(e)])

        if result:
            return CheckResult(self.name, "WARN", result)
        return CheckResult(self.name, "OK")


class InternalBackupsCheck(BaseCheck):
    name = "internal_backups"

    def __init__(self, vinfra, ctx=None):
        super().__init__(ctx)
        self.vinfra = vinfra

    def run(self):
        self.logger.info("Checking compute backup options")

        try:
            backup_service = self.vinfra.run("service", "compute", "backup", "show")
            backups = self.vinfra.run("service", "compute", "volume", "backup", "list", "-c", "status")
            problems = 0
            for backup in backups:
                if backup['status'].startswith('error'):
                    problems += 1
            if problems == 0:
                return CheckResult(self.name, "OK", [f"Backup driver: {backup_service['driver']}"])
            else:
                return CheckResult(self.name, "WARN", [f"Backup driver: {backup_service['driver']}",
                                                       f"Problematic backups: {problems}"])

        except Exception as e:
            if "Backup service is not enabled" in str(e):
                return CheckResult(self.name, "WARN", ["Compute backup service is not enabled"])
            return CheckResult(self.name, "ERROR", [str(e)])

class ExternalStorageCheck(BaseCheck):
    name = "external_storage"

    def __init__(self, vinfra, ctx=None):
        super().__init__(ctx)
        self.vinfra = vinfra

    def run(self):
        self.logger.info("Checking external storages")

        result = []
        try:
            storages = self.vinfra.run("service", "compute", "storage", "list")
            for storage in storages:
                if storage.get("status") != "available" and storage.get("enabled"):
                    result.append(f"External storage {storage.get('name')} status is not OK")

            if result:
                return CheckResult(self.name, "FAIL", result)

            return CheckResult(self.name, "OK")

        except Exception as e:
            return CheckResult(self.name, "ERROR", [str(e)])


class ComputeHealthCheck(BaseCheck):
    name = "compute_status"

    def __init__(self, vinfra, ctx=None):
        super().__init__(ctx)
        self.vinfra = vinfra

    def run(self):
        self.logger.info("Checking compute cluster status")

        try:
            compute_show = self.vinfra.run("service", "compute", "show")

            if compute_show["status"] != "active":
                return CheckResult(self.name, "WARN",
                                   [f"Compute state={compute_show['status']}"])

            return CheckResult(self.name, "OK")

        except Exception as e:
            return CheckResult(self.name, "ERROR", [str(e)])


class ComputeNodesCheck(BaseCheck):
    name = "compute_nodes"
    def __init__(self, vinfra, ctx=None):
        super().__init__(ctx)
        self.vinfra = vinfra

    def run(self):
        self.logger.info("Checking compute nodes health")

        problems = []
        try:
            compute_nodes = self.vinfra.run("service", "compute", "node", "list", "--long")
            for node in compute_nodes:
                host = node.get("host", "<unknown>")
                state = node.get("state")
                in_maintenance = node.get("in_maintenance", False)
                hypervisor = node.get("hypervisor") or {}
                hypervisor_state = hypervisor.get("state")
                services = node.get("services",[])

                node_problems = []

                if state != "healthy":
                    node_problems.append(f"state={state}")

                if in_maintenance:
                    node_problems.append("in_maintenance=True")

                if hypervisor and hypervisor_state != "up":
                    node_problems.append(f"hypervisor_state={hypervisor_state}")
                for service in services:
                    if service.get("state") != "healthy":
                        node_problems.append(f"service {service.get('name')}: {service.get('state')}")

                if node_problems:
                    problems.append(f"{host}: {', '.join(node_problems)}")
        except Exception as e:
            return CheckResult(self.name, "ERROR", [str(e)])
        if not problems:
            return CheckResult(self.name, "OK")
        else:
            return CheckResult(self.name, "FAIL", problems)

class ComputeClusterParams(BaseCheck):
    name = "compute_cluster_params"
    def __init__(self, vinfra, ctx=None):
        super().__init__(ctx)
        self.vinfra = vinfra

    def run(self):
        self.logger.info("Checking compute cluster addons")

        feature_names = {
            "backup": "Backups",
            "k8saas": "Kubernetes",
            "lbaas": "Load balancer",
            "metering": "Billing metering",
            "infra-optim": "Resource policies",
            "maas": "Migration service"
        }
        result = []
        try:
            compute = self.vinfra.run("service", "compute", "show")
            features = compute.get('features', [])
            if features:
                enabled_features = ', '.join([feature_names.get(f, f) for f in features])
                result.append(f"Compute cluster enabled features: {enabled_features}")
            cpu_model = compute.get('options',{}).get("cpu_model")
            if cpu_model:
                result.append(f"CPU model set: {cpu_model}")
            else:
                result.append("Compute cluster CPU model is not set")
                return CheckResult(self.name, "WARN", result)
            return CheckResult(self.name, "OK", result)

        except Exception as e:
            return CheckResult(self.name, "ERROR", [str(e)])








class RabbitmqClusterCheck(BaseCheck):
    name = "rabbitmq_cluster"

    CONTAINER_CHECK_CMD = "docker inspect -f '{{.State.Running}}' rabbitmq"
    CLUSTER_STATUS_CMD = (
        "docker exec -u root rabbitmq "
        "rabbitmqctl cluster_status --formatter json"
    )

    def __init__(self, nodes, ctx=None):
        super().__init__(ctx)
        self.nodes = nodes

    def run(self):
        self.logger.info("Checking RabbitMQ cluster status")

        ha_hosts = [
            node.get("host")
            for node in self.nodes
            if node.get("is_in_ha") is True and node.get("host")
        ]

        expected_count = len(ha_hosts)

        if expected_count == 0:
            return CheckResult(
                self.name,
                "WARN",
                ["No HA/management nodes found"],
            )

        problems = []
        cluster_views = {}

        for host in ha_hosts:
            try:
                container_result = run_ssh_command(
                    host,
                    self.CONTAINER_CHECK_CMD,
                    ssh_key=self.ctx.ssh_key,
                )

                if container_result.get("exit_code", 0) != 0:
                    problems.append(f"{host}: RabbitMQ container not found")
                    continue

                if container_result.get("stdout", "").strip() != "true":
                    problems.append(f"{host}: RabbitMQ container is not running")
                    continue

                status_result = run_ssh_command(
                    host,
                    self.CLUSTER_STATUS_CMD,
                    ssh_key=self.ctx.ssh_key,
                )

                if status_result.get("exit_code", 0) != 0:
                    problems.append(
                        f"{host}: cluster_status failed: "
                        f"{status_result.get('stderr', '').strip()}"
                    )
                    continue

                status = json.loads(status_result.get("stdout", ""))

                problems.extend(
                    self.check_status(
                        host=host,
                        status=status,
                        expected_count=expected_count,
                    )
                )

                cluster_views[host] = self.cluster_signature(status)

            except json.JSONDecodeError as exc:
                problems.append(f"{host}: cannot parse RabbitMQ JSON: {exc}")
            except Exception as exc:
                self.logger.exception("RabbitMQ check failed on %s", host)
                problems.append(f"{host}: RabbitMQ check failed: {exc}")

        problems.extend(self.check_cluster_views(cluster_views))

        if problems:
            return CheckResult(self.name, "FAIL", problems)

        return CheckResult(
            self.name,
            "OK",
            [f"RabbitMQ cluster is healthy on {expected_count} HA nodes"],
        )

    @staticmethod
    def check_status(host, status, expected_count):
        problems = []

        alarms = status.get("alarms") or []
        if alarms:
            problems.append(f"{host}: RabbitMQ alarms are present: {alarms}")

        partitions = status.get("partitions") or {}
        if partitions:
            problems.append(f"{host}: RabbitMQ network partitions detected: {partitions}")

        disk_nodes = set(status.get("disk_nodes") or [])
        running_nodes = set(status.get("running_nodes") or [])

        if len(disk_nodes) != expected_count:
            problems.append(
                f"{host}: disk_nodes count is {len(disk_nodes)}, "
                f"expected {expected_count}"
            )

        if len(running_nodes) != expected_count:
            problems.append(
                f"{host}: running_nodes count is {len(running_nodes)}, "
                f"expected {expected_count}"
            )

        if disk_nodes != running_nodes:
            problems.append(
                f"{host}: disk_nodes and running_nodes differ: "
                f"disk_nodes={sorted(disk_nodes)}, "
                f"running_nodes={sorted(running_nodes)}"
            )

        maintenance_status = status.get("maintenance_status") or {}
        nodes_in_maintenance = {
            node: state
            for node, state in maintenance_status.items()
            if state != "not under maintenance"
        }

        if nodes_in_maintenance:
            problems.append(
                f"{host}: RabbitMQ nodes in maintenance: {nodes_in_maintenance}"
            )

        versions = status.get("versions") or {}

        rabbit_versions = {
            node: data.get("rabbitmq_version")
            for node, data in versions.items()
        }

        erlang_versions = {
            node: data.get("erlang_version")
            for node, data in versions.items()
        }

        if len(set(rabbit_versions.values())) > 1:
            problems.append(f"{host}: RabbitMQ version mismatch: {rabbit_versions}")

        if len(set(erlang_versions.values())) > 1:
            problems.append(f"{host}: Erlang version mismatch: {erlang_versions}")

        return problems

    @staticmethod
    def cluster_signature(status):
        return {
            "disk_nodes": sorted(status.get("disk_nodes") or []),
            "running_nodes": sorted(status.get("running_nodes") or []),
        }

    @staticmethod
    def check_cluster_views(cluster_views):
        problems = []

        if not cluster_views:
            problems.append("Could not get RabbitMQ cluster status from any HA node")
            return problems

        unique_views = {
            json.dumps(view, sort_keys=True)
            for view in cluster_views.values()
        }

        if len(unique_views) > 1:
            problems.append(
                f"RabbitMQ cluster view differs between HA nodes: {cluster_views}"
            )

        return problems




class RabbitmqQueueCheck(BaseCheck):
    name = "rabbitmq_queues"

    DEFAULT_NOVA_CONF = "/etc/kolla/nova-conductor/nova.conf"
    DEFAULT_CONTAINER = "rabbitmq"

    def __init__(self, ctx=None, conf_path=None, container=None):
        super().__init__(ctx)
        self.conf_path = Path(conf_path or self.DEFAULT_NOVA_CONF)
        self.container = container or self.DEFAULT_CONTAINER

    def run(self):
        self.logger.info("Checking RabbitMQ queues")

        try:
            transport_url = self.read_transport_url(self.conf_path)
            api_url, username, password = self.parse_rabbitmq_api(transport_url)

            api_queues = self.fetch_api_queues(api_url, username, password)
            ctl_queues = self.fetch_rabbitmqctl_queues()

            quorum_open_files_null = self.find_quorum_open_files_null(api_queues)
            not_running = self.find_not_running(ctl_queues)

        except Exception as exc:
            self.logger.exception("RabbitMQ queue check failed")
            return CheckResult(
                self.name,
                "ERROR",
                [f"RabbitMQ queue check failed: {exc}"],
            )

        details = []

        if quorum_open_files_null:
            details.append(
                f"Quorum queues with open_files=null: {len(quorum_open_files_null)}"
            )
            for queue in quorum_open_files_null:
                details.append(
                    "quorum open_files=null: "
                    f"vhost={queue.get('vhost')}, "
                    f"name={queue.get('name')}, "
                    f"state={queue.get('state')}, "
                    f"messages={queue.get('messages')}, "
                    f"node={queue.get('node')}, "
                    f"leader={queue.get('leader')}"
                )

        if not_running:
            details.append(f"Queues not running: {len(not_running)}")
            for queue in not_running:
                details.append(
                    "queue not running: "
                    f"name={queue.get('name')}, "
                    f"state={queue.get('state')}, "
                    f"messages={queue.get('messages')}"
                )

        if details:
            return CheckResult(self.name, "FAIL", details)

        return CheckResult(
            self.name,
            "OK",
            ["All checked RabbitMQ queues are healthy"],
        )

    @staticmethod
    def read_transport_url(conf_path: Path) -> str:
        parser = configparser.ConfigParser()
        parser.read(conf_path)

        if parser.has_option("DEFAULT", "transport_url"):
            return parser.get("DEFAULT", "transport_url").strip()

        for line in conf_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("transport_url"):
                return line.split("=", 1)[1].strip()

        raise RuntimeError(f"transport_url not found in {conf_path}")

    @staticmethod
    def parse_rabbitmq_api(transport_url: str):
        if not transport_url.startswith("rabbit://"):
            raise RuntimeError(f"Unsupported transport_url: {transport_url}")

        raw = transport_url[len("rabbit://"):]
        raw = raw.split("?", 1)[0]

        hosts_part = raw.split("/", 1)[0]
        first_host = hosts_part.split(",", 1)[0]

        if "@" not in first_host:
            raise RuntimeError("No credentials found in transport_url")

        creds, hostport = first_host.rsplit("@", 1)

        if ":" in creds:
            username, password = creds.split(":", 1)
        else:
            username, password = creds, ""

        host = hostport.split(":", 1)[0]
        api_url = f"http://{host}:15672/api/queues/"

        return api_url, unquote(username), unquote(password)

    @staticmethod
    def fetch_api_queues(api_url: str, username: str, password: str):
        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, api_url, username, password)

        opener = urllib.request.build_opener(
            urllib.request.HTTPBasicAuthHandler(password_mgr)
        )

        with opener.open(api_url, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def fetch_rabbitmqctl_queues(self):
        result = run_cmd([
            "docker",
            "exec",
            "-u",
            "root",
            self.container,
            "rabbitmqctl",
            "list_queues",
            "name",
            "state",
            "messages",
            "--formatter",
            "json",
        ], parsejson=True)

        return result

    @staticmethod
    def find_quorum_open_files_null(api_queues):
        result = []

        for queue in api_queues:
            if queue.get("type") == "quorum" and queue.get("open_files") is None:
                result.append({
                    "vhost": queue.get("vhost"),
                    "name": queue.get("name"),
                    "type": queue.get("type"),
                    "state": queue.get("state"),
                    "messages": queue.get("messages"),
                    "messages_ready": queue.get("messages_ready"),
                    "messages_unacknowledged": queue.get("messages_unacknowledged"),
                    "consumers": queue.get("consumers"),
                    "open_files": queue.get("open_files"),
                    "node": queue.get("node"),
                    "leader": queue.get("leader"),
                })

        return result

    @staticmethod
    def find_not_running(ctl_queues):
        return [
            {
                "name": queue.get("name"),
                "state": queue.get("state"),
                "messages": queue.get("messages"),
            }
            for queue in ctl_queues
            if queue.get("state") != "running"
        ]