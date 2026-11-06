from .framework import BaseCheck, CheckResult
from openstack.exceptions import SDKException
import ipaddress
from urllib.parse import urlparse
class OpenStackComputeServiceCheck(BaseCheck):
    name = "openstack_compute_services"

    IGNORED_BINARIES = {
        "nova-fileproxy",
    }

    def __init__(self, conn, ctx=None):
        super().__init__(ctx)
        self.conn = conn

    def run(self):
        self.logger.info("Checking OpenStack Compute services")

        if self.conn is None:
            return CheckResult(
                self.name,
                "ERROR",
                ["OpenStack connection is not initialized"],
            )

        try:
            services = list(self.conn.compute.services())
        except Exception as exc:
            self.logger.exception("Failed to list OpenStack Compute services")
            return CheckResult(
                self.name,
                "ERROR",
                [f"Failed to list Compute services: {exc}"],
            )

        down_services = []

        for service in services:
            binary = service.binary
            host = service.host
            state = service.state

            if state == "down" and binary not in self.IGNORED_BINARIES:
                down_services.append(
                    f"{binary} on {host}"
                )

        if down_services:
            return CheckResult(
                self.name,
                "FAIL",
                down_services,
            )

        return CheckResult(
            self.name,
            "OK"
        )

class OpenStackComputeAPIDNSCheck(BaseCheck):
    name = "openstack_compute_dns"

    def __init__(self, conn, ctx=None):
        super().__init__(ctx)
        self.conn = conn

    def run(self):
        self.logger.info("Checking OpenStack public API endpoint names")

        if self.conn is None:
            return CheckResult(
                self.name,
                "ERROR",
                ["OpenStack connection is not initialized"],
            )

        try:
            endpoints = [
                endpoint
                for endpoint in self.conn.identity.endpoints()
                if endpoint.interface == "public" and endpoint.url.startswith('https')
            ]
        except SDKException as exc:
            self.logger.exception("Failed to list OpenStack endpoints")
            return CheckResult(
                self.name,
                "ERROR",
                [f"Failed to list OpenStack public endpoints: {exc}"],
            )
        except Exception as exc:
            self.logger.exception("Unexpected OpenStack endpoint error")
            return CheckResult(
                self.name,
                "ERROR",
                [f"Unexpected endpoint query error: {exc}"],
            )

        if not endpoints:
            return CheckResult(
                self.name,
                "FAIL",
                ["No public OpenStack endpoints found"],
            )

        ip_endpoints = []
        dns_endpoints = []
        invalid_endpoints = []

        for endpoint in endpoints:
            url = endpoint.url

            if not url:
                invalid_endpoints.append(
                    f"Endpoint {endpoint.id}: URL is empty"
                )
                continue

            parsed = urlparse(url)
            host = parsed.hostname

            if not host:
                invalid_endpoints.append(
                    f"Cannot determine hostname from endpoint URL: {url}"
                )
                continue

            try:
                ipaddress.ip_address(host)
                ip_endpoints.append(f"{host}")
            except ValueError:
                dns_endpoints.append(f"{host}")

        details = []

        if dns_endpoints:
            details.append(
                "Public API endpoints using DNS names: "
                + ", ".join(sorted(set(dns_endpoints)))
            )

        if ip_endpoints:
            details.append(
                "Public API endpoints using IP addresses: "
                + ", ".join(sorted(set(ip_endpoints)))
            )

        details.extend(invalid_endpoints)

        if invalid_endpoints:
            return CheckResult(
                self.name,
                "FAIL",
                details,
            )

        if ip_endpoints:
            return CheckResult(
                self.name,
                "WARN",
                details,
            )

        return CheckResult(
            self.name,
            "OK",
            details,
        )


class OpenStackVolumeServiceCheck(BaseCheck):
    name = "openstack_volume_services"

    def __init__(self, conn, ctx=None):
        super().__init__(ctx)
        self.conn = conn

    def run(self):
        self.logger.info("Checking OpenStack Volume services")

        if self.conn is None:
            return CheckResult(
                self.name,
                "ERROR",
                ["OpenStack connection is not initialized"],
            )

        try:
            response = self.conn.block_storage.get("/os-services")
            payload = response.json()
            services = payload.get("services") or []

        except Exception as exc:
            self.logger.exception("Failed to list Cinder services")
            return CheckResult(
                self.name,
                "ERROR",
                [f"Failed to list Volume services: {exc}"],
            )

        if not services:
            return CheckResult(
                self.name,
                "WARN",
                ["No Cinder services returned by /os-services"],
            )

        down_services = []
        disabled_services = []

        for service in services:
            binary = service.get("binary", "unknown")
            host = service.get("host", "unknown")
            state = service.get("state")
            status = service.get("status")

            service_name = f"{binary} on {host}"

            if state == "down":
                down_services.append(service_name)

            if status == "disabled":
                disabled_services.append(service_name)

        details = []

        details.extend(
            f"Down: {service}"
            for service in down_services
        )
        details.extend(
            f"Disabled: {service}"
            for service in disabled_services
        )

        if down_services:
            return CheckResult(
                self.name,
                "FAIL",
                details,
            )

        if disabled_services:
            return CheckResult(
                self.name,
                "WARN",
                details,
            )

        return CheckResult(
            self.name,
            "OK",
        )

class OpenStackNetworkAgentCheck(BaseCheck):
    name = "openstack_network_agents"

    def __init__(self, conn, ctx=None):
        super().__init__(ctx)
        self.conn = conn

    def run(self):
        self.logger.info("Checking OpenStack Network agents")

        try:
            agents = list(self.conn.network.agents())
        except Exception as exc:
            self.logger.exception("Failed to list Network agents")
            return CheckResult(
                self.name,
                "ERROR",
                [f"Failed to list Network agents: {exc}"],
            )

        down_agents = []

        for agent in agents:
            alive = getattr(agent, "is_alive", None)

            if alive is None:
                alive = getattr(agent, "alive", False)

            if not alive:
                down_agents.append(
                    f"{getattr(agent, 'agent_type', 'unknown')} "
                    f"on {getattr(agent, 'host', 'unknown')}"
                )

        if down_agents:
            return CheckResult(
                self.name,
                "FAIL",
                down_agents,
            )

        return CheckResult(
            self.name,
            "OK",
        )