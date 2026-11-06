from .framework import BaseCheck, CheckResult
from utils import run_ssh_command, run_cmd
import json

class LicenseCheck(BaseCheck):
    name = "license"

    def __init__(self, vinfra, ctx=None):
        super().__init__(ctx)
        self.vinfra = vinfra

    def run(self):
        self.logger.info("Check license status")

        try:
            license = self.vinfra.run("cluster", "license", "show")
            if license["status"] != "active":
                return CheckResult(self.name, "FAIL",
                                   [f"License status: {license['status']}"])
            return CheckResult(self.name, "OK")
        except Exception as e:
            return CheckResult(self.name, "ERROR", [str(e)])

class GatewayCheck(BaseCheck):
    name = "gateways"

    def __init__(self, vinfra, nodes, all_interfaces, ctx=None):
        super().__init__(ctx)
        self.vinfra = vinfra
        self.nodes = nodes
        self.all_interfaces = all_interfaces

    def run(self):
        self.logger.info("Check infrastructure nodes interfaces gateways")

        result = []
        interfaces = self.all_interfaces
        gateway_count = dict.fromkeys([node['id'] for node in self.nodes], 0)
        for iface in interfaces:
            if iface['gw4']:
                gateway_count[iface['node_id']] +=1
        for node in self.nodes:
            if gateway_count[node["id"]] == 0:
                result.append(f"No gateway on {node['host']}")
            elif gateway_count[node["id"]] > 1:
                result.append(f"Multiple gateways on {node['host']}")
        if result:
            return CheckResult(self.name, "FAIL", result)
        return CheckResult(self.name, "OK")

class InterfaceAggregationCheck(BaseCheck):
    name = "interface_bonds"

    def __init__(self, vinfra, nodes, all_interfaces, ctx=None):
        super().__init__(ctx)
        self.vinfra = vinfra
        self.nodes = nodes
        self.all_interfaces = all_interfaces
        self.node_map = {
            n["id"]: n["host"]
            for n in self.nodes
        }

    def run(self):
        self.logger.info("Check infrastructure interfaces aggregation")

        result = []
        interfaces = self.all_interfaces
        networks = self.vinfra.run("cluster", "network", "list")
        network_map = {n["id"]: n["name"] for n in networks}
        for interface in interfaces:
            if not interface["network"]:
                continue
            if interface["name"].find("bond") <0:
                host = self.node_map.get(interface["node_id"])
                network = network_map.get(interface["network"])
                result.append(f"Interface {interface['name']} on {host} network {network} is not aggregated")

        if result:
            return CheckResult(self.name, "FAIL", result)
        return CheckResult(self.name, "OK")



class AlertsCheck(BaseCheck):
    name = "alerts"

    def __init__(self, vinfra, ctx=None):
        super().__init__(ctx)
        self.vinfra = vinfra

    def run(self):
        self.logger.info("Checking critical and warning alerts")

        counter = [0,0]
        alerts = self.vinfra.run("cluster", "alert",  "list", "-c", "severity")
        for alert in alerts:
            if alert['severity'] == 'warning':
                counter[0] += 1
            elif alert['severity'] == 'error':
                counter[1] += 1
        if counter[1] > 0:
            return CheckResult(self.name, "FAIL", [ f"Errors: {counter[1]}", f"Warnings: {counter[0]}"])
        if counter[0] > 0:
            return CheckResult(self.name, "WARN", [ f"Warnings: {counter[0]}" ])
        else:
            return CheckResult(self.name, "OK")

class InfraNodeCheck(BaseCheck):
    name = "infra_nodes"

    def __init__(self, nodes, ctx=None):
        super().__init__(ctx)
        self.nodes = nodes

    def run(self):
        self.logger.info("Checking if all infrastructure nodes are online")

        offline = [n["host"] for n in self.nodes if not n["is_online"]]
        if offline:
            return CheckResult(self.name, "FAIL", offline)
        return CheckResult(self.name, "OK")


class TimeSyncCheck(BaseCheck):
    name = "time_sync"

    UTC_TIMEZONES = {"UTC", "Etc/UTC"}

    def __init__(self, hosts, ctx=None):
        super().__init__(ctx)
        self.hosts = hosts

    def run(self):
        self.logger.info("Checking time synchronization and time zones")

        problems = []
        warnings = []
        timezones = {}

        for host in self.hosts:
            try:
                result = run_ssh_command(
                    host,
                    "timedatectl show",
                    ssh_key=self.ctx.ssh_key,
                )

                stdout = result["stdout"]

                if "NTPSynchronized=no" in stdout:
                    problems.append(f"{host}: NTP is not synchronized")

                for line in stdout.splitlines():
                    line = line.strip()
                    if line.startswith("Timezone="):
                        timezones[host] = line[len("Timezone="):].strip()
                        break

            except Exception as exc:
                problems.append(f"{host}: failed to check time settings: {exc}")

        non_utc_timezones = {
            host: timezone
            for host, timezone in timezones.items()
            if timezone not in self.UTC_TIMEZONES
        }

        if non_utc_timezones:
            warnings.append(
                "Non-UTC time zones configured: "
                + ", ".join(
                    f"{host}={timezone}"
                    for host, timezone in sorted(non_utc_timezones.items())
                )
            )

        details = problems + warnings

        if problems:
            return CheckResult(self.name, "FAIL", details)

        if warnings:
            return CheckResult(self.name, "WARN", details)

        return CheckResult(self.name, "OK")
class HAStateCheck(BaseCheck):
    name = "ha_state"

    def __init__(self, vinfra, ctx=None):
        super().__init__(ctx)
        self.vinfra = vinfra

    def run(self):
        self.logger.info("Checking infrastructure high availability")

        try:
            ha = self.vinfra.run("cluster", "ha", "show")
            ha_size = len(ha['nodes'])

            return CheckResult(self.name, "OK", [f'Number of nodes in Management High Availability Cluster: {ha_size}'])

        except Exception as e:
            return CheckResult(self.name, "ERROR", [str(e)])



class ShamanCheck(BaseCheck):
    name = "shaman_check"

    def __init__(self, hosts, ctx=None):
        super().__init__(ctx)
        self.hosts = hosts

    def run(self):
        self.logger.info("Checking shaman status")

        problems = []
        out = []
        shaman = run_cmd(["shaman", "stat", "-j"], parsejson=True)["status"]["nodes"]
        for node in shaman:
            out.append({'hostname': shaman[node]['annotations']['node-hostname'],
                        'status': shaman[node]['status']})
        if len(out) != len(self.hosts):
            problems.append(f"Number of nodes in shaman is wrong. Cluster size = {len(self.hosts)}, "
                            f"in shaman {len(out)}")
        for node in out:
            if node["status"] != "Active":
                problems.append(f"Shaman status on node {node['hostname']} : {node['status']}")

        if problems:
            return CheckResult(self.name, "FAIL", problems)
        else:
            return CheckResult(self.name, "OK")
class NetworkBondCheck(BaseCheck):
    name = "network_bonds"
    REQUIRED_MODE = "802.3ad"



    def __init__(self, hosts, ctx=None):
        super().__init__(ctx)
        self.hosts = hosts

    def run(self):
        self.logger.info("Checking network bonds")

        problems = []
        min_slaves = 1
        expected_ports = 2
        for host in self.hosts:
            try:
                result = run_ssh_command(host, "ls /proc/net/bonding", ssh_key=self.ctx.ssh_key)
                bonds = result["stdout"].split()

                for bond_iface in bonds:
                    data = run_ssh_command(
                        host,
                        f"cat /proc/net/bonding/{bond_iface}", ssh_key=self.ctx.ssh_key
                    )["stdout"]
                    bond = {
                        "mode": None,
                        "xmit_hash_policy": None,
                        "mii_status": None,
                        "active_aggregator": None,
                        "active_ports": None,
                        "slaves": []
                    }
                    current_slave = None
                    in_active_agg_section = False
                    for line in data.split('\n'):
                        if not line:
                            continue
                        line = line.strip()
                        if line.startswith("Bonding Mode:"):
                            bond["mode"] = line.split(":", 1)[1].strip()
                        elif line.startswith("Transmit Hash Policy:"):
                            bond["xmit_hash_policy"] = line.split(":", 1)[1].strip()
                        elif line.startswith("MII Status:") and current_slave is None:
                            bond["mii_status"] = line.split(":", 1)[1].strip()
                        elif line.startswith("Active Aggregator Info"):
                            in_active_agg_section = True
                        elif in_active_agg_section and line.startswith("Aggregator ID:"):
                            bond["active_aggregator"] = line.split(":", 1)[1].strip()
                        elif in_active_agg_section and line.startswith("Number of ports:"):
                            value = line.split(":", 1)[1].strip()
                            bond["active_ports"] = int(value)
                            in_active_agg_section = False
                        elif line.startswith("Slave Interface:"):
                            if current_slave:
                                bond["slaves"].append(current_slave)
                            current_slave = {
                                "name": line.split(":", 1)[1].strip(),
                                "mii_status": None,
                                "speed": None,
                                "duplex": None,
                                "aggregator_id": None,
                                "link_failures": None
                            }
                        elif current_slave:
                            if line.startswith("MII Status:"):
                                current_slave["mii_status"] = line.split(":", 1)[1].strip()
                            elif line.startswith("Speed:"):
                                val = line.split(":", 1)[1].strip().split()[0]
                                try:
                                    current_slave["speed"] = int(val)
                                except (IndexError, ValueError):
                                    current_slave["speed"] = None
                            elif line.startswith("Duplex:"):
                                current_slave["duplex"] = line.split(":", 1)[1].strip()
                            elif line.startswith("Aggregator ID:"):
                                current_slave["aggregator_id"] = line.split(":", 1)[1].strip()
                            elif line.startswith("Link Failure Count:"):
                                val = line.split(":", 1)[1].strip()
                                current_slave["link_failures"] = int(val)
                    if current_slave:
                        bond["slaves"].append(current_slave)
                    errors = []
                    if not bond["mode"] or "802.3ad" not in bond["mode"]:
                        errors.append("Bond is not in 802.3ad mode")
                    if not bond["xmit_hash_policy"] or "layer3+4" not in bond["xmit_hash_policy"]:
                        errors.append("Transmit hash policy is not layer3+4")
                    if bond["mii_status"] != "up":
                        errors.append("Bond MII status is not up")
                    active_agg = bond["active_aggregator"]
                    if not active_agg:
                        errors.append("No active aggregator found")
                    if bond["active_ports"] is None:
                        errors.append("Could not determine number of active ports")
                    elif bond["active_ports"] < expected_ports:
                        errors.append(
                            f"LACP degraded: only {bond['active_ports']} active ports "
                            f"(expected {expected_ports})"
                        )
                    slaves = bond["slaves"]
                    if len(slaves) < min_slaves:
                        errors.append(f"Only {len(slaves)} slaves found (expected ≥ {min_slaves})")
                    active_slaves = 0
                    for slave in slaves:
                        name = slave["name"]
                        if slave["mii_status"] != "up":
                            errors.append(f"{name}: link down")
                        else:
                            active_slaves += 1
                        if not slave["speed"] or slave["speed"] <= 0:
                            errors.append(f"{name}: invalid speed")
                        if slave["duplex"] != "full":
                            errors.append(f"{name}: not full duplex")
                        if active_agg and slave["aggregator_id"] != active_agg:
                            errors.append(f"{name}: aggregator mismatch")
                    if active_slaves < min_slaves:
                        errors.append(f"Only {active_slaves} active slaves (expected ≥ {min_slaves})")
                    if errors:
                        problems.append({'host': host, 'bond': bond_iface, 'errors': errors})


            except Exception as e:
                problems.append(f"{host}: {str(e)}")

        if problems:
            return CheckResult(self.name, "FAIL", problems)

        return CheckResult(self.name, "OK")


class NodesStorageServicesCheck(BaseCheck):
    name = "nodes_storage_services"
    def __init__(self, nodes, ctx=None):
        super().__init__(ctx)
        self.nodes = nodes


    def run(self):
        self.logger.info("Checking storage services")
        services_map = {
            'nfs': 'NFS',
            's3': 'S3',
        }
        result = []
        for node in self.nodes:
            roles = node.get("roles", {})
            abgw = roles.get('abgw')
            if abgw and abgw.get('active') != 1:
                result.append(f"Host: {node['host']} service Acronis Backup Gateway problems")

            for services in services_map:
                role_status = roles.get(services)
                if not role_status:
                    continue
                service_problems = False

                for item in role_status.values():
                    if not isinstance(item, dict):
                        continue
                    total = item.get("total")
                    active = item.get("active")
                    if total is not None and active is not None:
                        if total != active:
                            service_problems = True
                if service_problems:
                    result.append(f"Host: {node['host']} service {services_map.get(services)} problems")

        if result:
            return CheckResult(self.name, "FAIL", result)

        return CheckResult(self.name, "OK")

class KAAccessCheck(BaseCheck):
    name = "access_to_ka"

    def __init__(self,hosts, ctx=None):
        super().__init__(ctx)
        self.hosts = hosts

    def run(self):
        self.logger.info("Checking access to Key Administrator")
        problems = []
        for server in self.hosts:
            check = run_ssh_command(server,
                                    "curl https://ka.virtuozzo.com:5224/heartbeat",
                                    timeout= 30,
                                    ssh_key=self.ctx.ssh_key)
#            if check["exit_code"] != 0 or check["stdout"].find('Virtuozzo Key Administrator') < 0:
            if check["exit_code"] != 0 or check["stdout"].find('HEALTHY') < 0:
                    problems.append(f"Problem with access to Virtuozzo Key Administrator from {server}")
        if problems:
            return CheckResult(self.name, "FAIL", problems)
        return CheckResult(self.name, "OK")


class YumCheck(BaseCheck):
    name = "yum_repos_check"

    VALID_REPOS = {
        "hci-base",
        "hci-updates",
    }

    def __init__(self, hosts, ctx=None):
        super().__init__(ctx)
        self.hosts = hosts

    @staticmethod
    def parse_enabled_repos(output):
        repos = set()
        in_repo_list = False

        for line in output.splitlines():
            line = line.strip()

            if not line:
                continue

            if line.lower().startswith("repo id"):
                in_repo_list = True
                continue

            if not in_repo_list:
                continue

            if line.lower().startswith("repolist:"):
                break

            repo_id = line.split()[0]
            repos.add(repo_id)

        return repos

    def run(self):
        self.logger.info("Checking yum repositories")

        problems = []

        for host in self.hosts:
            try:
                result = run_ssh_command(
                    host,
                    "yum repolist --enabled -C",
                    ssh_key=self.ctx.ssh_key,
                )

                stdout = result.get("stdout", "")
                stderr = result.get("stderr", "")
                exit_code = result.get("exit_code", 0)

                if exit_code != 0:
                    problems.append(
                        f"{host}: yum command failed with rc={exit_code}: {stderr.strip()}"
                    )
                    continue

                enabled_repos = self.parse_enabled_repos(stdout)

                missing_repos = self.VALID_REPOS - enabled_repos
                extra_repos = enabled_repos - self.VALID_REPOS

                if missing_repos or extra_repos:
                    details = []

                    if missing_repos:
                        details.append(f"missing={sorted(missing_repos)}")

                    if extra_repos:
                        details.append(f"extra={sorted(extra_repos)}")

                    problems.append(
                        f"{host}: enabled={sorted(enabled_repos)}, "
                        f"expected={sorted(self.VALID_REPOS)} "
                        f"({', '.join(details)})"
                    )

            except Exception as exc:
                self.logger.exception("Failed to check yum repositories on %s", host)
                problems.append(f"{host}: failed to check yum repositories: {exc}")

        if problems:
            problems.append(
                f"Only these repositories should be enabled: {sorted(self.VALID_REPOS)}"
            )
            return CheckResult(self.name, "FAIL", problems)

        return CheckResult(
            self.name,
            "OK",
            [f"All hosts have only expected repositories enabled: {sorted(self.VALID_REPOS)}"],
        )


class BackendInitCheck(BaseCheck):
    name = "backendinit_check"

    INITFILE = "/usr/libexec/vstorage-ui-backend/etc/backend.init"

    def __init__(self, hosts, ctx=None):
        super().__init__(ctx)
        self.hosts = hosts

    def run(self):
        self.logger.info("Looking for not initialized backends")

        problems = []

        for host in self.hosts:
            try:
                result = run_ssh_command(
                    host,
                    f"test -f {self.INITFILE}",
                    ssh_key=self.ctx.ssh_key,
                )

                if result.get("exit_code", 0) == 0:
                    problems.append(f"File {self.INITFILE} found on {host}")

            except Exception as exc:
                problems.append(f"{host}: failed to check {self.INITFILE}: {exc}")

        if problems:
            return CheckResult(self.name, "FAIL", problems)

        return CheckResult(
            self.name,
            "OK",
        )

class AgentRegistrationCheck(BaseCheck):
    name = "agent_registration_check"

    REGISTRATIONFILE = "/usr/libexec/vstorage-ui-agent/etc/registration.conf"

    def __init__(self, hosts, ctx=None):
        super().__init__(ctx)
        self.hosts = hosts

    def run(self):
        self.logger.info("Looking for not initialized backends")

        problems = []

        for host in self.hosts:
            try:
                result = run_ssh_command(
                    host,
                    f"test -f {self.REGISTRATIONFILE}",
                    ssh_key=self.ctx.ssh_key,
                )

                if result.get("exit_code", 0) == 0:
                    problems.append(f"File {self.REGISTRATIONFILE} found on {host}")

            except Exception as exc:
                problems.append(f"{host}: failed to check {self.REGISTRATIONFILE}: {exc}")

        if problems:
            return CheckResult(self.name, "FAIL", problems)

        return CheckResult(
            self.name,
            "OK",
        )



class SoftwareUpdateCheck(BaseCheck):
    name = "software_update_state"

    def __init__(self, vinfra, ctx=None):
        super().__init__(ctx)
        self.vinfra = vinfra

    @staticmethod
    def get_version(entity):
        release_info = entity.get("current_storage_release") or entity.get("installed_storage_release") or {}

        version = release_info.get("version")
        release = release_info.get("release")

        if version and release:
            return f"{version}-{release}"
        if version:
            return str(version)
        return "unknown"

    def run(self):
        self.logger.info("Checking software updates status")

        details = []
        errors = []
        versions = set()

        try:
            sus = self.vinfra.run("software-updates", "status")

            management_panel = sus.get("control_plane") or {}
            mp_version = self.get_version(management_panel)
            versions.add(mp_version)
            details.append(f"Management Panel Version: {mp_version}")

            for node in sus.get("nodes") or []:
                host = node.get("host", "unknown")
                node_version = self.get_version(node)

                versions.add(node_version)
                details.append(f"Node {host} version: {node_version}")

                error = node.get("error") or {}
                if error:
                    errors.append(
                        f"Node {host} update error: {error.get('message', error)}"
                    )

        except Exception as exc:
            return CheckResult(
                self.name,
                "ERROR",
                [f"Failed to get software update status: {exc}"],
            )

        details.extend(errors)

        if errors:
            return CheckResult(self.name, "FAIL", details)

        if len(versions) > 1:
            details.append(
                f"Mixed software versions detected: {', '.join(sorted(versions))}"
            )
            return CheckResult(self.name, "WARN", details)

        return CheckResult(self.name, "OK", details)
