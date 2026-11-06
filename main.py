import argparse
import logging
import sys
import time
from pathlib import Path
import openstack
from check.compute import (
    ComputeClusterParams,
    ComputeHealthCheck,
    ComputeNodesCheck,
    ComputeParamsCheck,
    ExternalStorageCheck,
    InternalBackupsCheck,
    RabbitmqClusterCheck,
    RabbitmqQueueCheck,
)
from check.framework import (
    print_summary,
    run_selected_checks,
    run_selected_exports,
)
from check.infra import (
    AlertsCheck,
    GatewayCheck,
    HAStateCheck,
    InfraNodeCheck,
    InterfaceAggregationCheck,
    KAAccessCheck,
    LicenseCheck,
    NetworkBondCheck,
    NodesStorageServicesCheck,
    ShamanCheck,
    TimeSyncCheck,
    YumCheck,
    BackendInitCheck,
    AgentRegistrationCheck,
    SoftwareUpdateCheck,
)
from check.openstack import (
    OpenStackComputeAPIDNSCheck,
    OpenStackComputeServiceCheck,
    OpenStackNetworkAgentCheck,
    OpenStackVolumeServiceCheck,
)
from check.storage import (
    ChunkServerErrorCheck,
    DisksHealthCheck,
    IOQueueDepthCheck,
    MDSHealthCheck,
    ReplicaOneFilesCheck,
    StorageClusterStatusCheck,
    TierFreeSpaceCheck,
)
from context import HealthCheckContext
from exporter.cluster import AlertsExporter, ClusterOverviewExporter, HAExporter
from exporter.compute import (
    ComputeNetworksExporter,
    ComputeNodeExporter,
    ComputeStoragePoliciesExporter,
    ComputeShowExporter,
    ComputeStatExporter,
)
from exporter.hardware import (
    HardwareExporter, NetworkBondExporter, EthernetsExporter, StorageHardwareExporter,
)
from exporter.infra import (
    InfraNetworksExporter,
    InterfacesExporter,
    NodeExporter,
)
from exporter.license import (
    LicenseExporter,
)
from exporter.storage import (
    DisksExporter,
    VstorageGetEvent,
    ExternalStorageExporter,
    VstorageStat,
    VstorageConfig,
)
#from exporter.versions import (
#    VersionsExporter,
#)
from logging_config import setup_logging
from utils import (
    load_openrc, get_cluster_name, vstorage_stats, DEFAULT_OPENRC_SCRIPT, DEFAULT_SSH_KEY
)
from vinfra_wrapper import Vinfra

EXPORT_DIR = Path("./exports")
COMPUTE_CHECKS = {
    "ComputeNodesCheck",
    "ComputeHealthCheck",
    "OpenStackComputeAPIDNSCheck",
    "OpenStackComputeServiceCheck",
    "OpenStackVolumeServiceCheck",
    "OpenStackNetworkAgentCheck",
    "InternalBackupsCheck",
    "ExternalStorageCheck",
    "ComputeParamsCheck",
    "ComputeClusterParams",
    "RabbitmqClusterCheck",
    "RabbitmqQueueCheck",
}

COMPUTE_EXPORTERS = {
    "ComputeNetworksExporter",
    "ExternalStorageExporter",
    "ComputeNodeExporter",
    "ComputeStoragePoliciesExporter",
    "ComputeShowExporter",
    "ComputeStatExporter",
}
def parse_args():
    parser = argparse.ArgumentParser(
        description="Virtuozzo Infrastructure Health Check Tool"
    )

    parser.add_argument(
        "-c",
        "--check",
        help="Run only specific check, for example: LicenseCheck",
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List available checks",
    )
    parser.add_argument(
        "-n",
        "--noexports",
        action="store_true",
        help="Do not export data",
    )
    parser.add_argument(
        "--listexports",
        action="store_true",
        help="List available exports",
    )
    parser.add_argument(
        "-e",
        "--export",
        help="Execute only specific exporter",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--nocompute",
        action="store_true",
        help="Run in infrastructure/storage-only mode without Compute checks and exports",
    )
    parser.add_argument(
        "--ssh-key",
        default=DEFAULT_SSH_KEY,
        help=f"SSH private key path (default: {DEFAULT_SSH_KEY})",
    )

    parser.add_argument(
        "--openrc",
        default=DEFAULT_OPENRC_SCRIPT,
        help=f"OpenStack openrc file (default: {DEFAULT_OPENRC_SCRIPT})",
    )
    return parser.parse_args()


def build_context(runtime_ctx):

    load_openrc(runtime_ctx.openrc_path)

    vinfra = Vinfra()
    cluster_name = get_cluster_name()
    nodes = vinfra.run("node", "list", "--long", "--sort-column", "host")
    hosts = [node["host"] for node in nodes]
    cluster_overview = vinfra.run("cluster", "overview")
    vstorage_stat = vstorage_stats(cluster_name)
    openstack_conn = None
    all_interfaces = vinfra.run("node", "iface", "list", "-a", "--long",)

    if not runtime_ctx.no_compute:
        openstack_conn = openstack.connect(verify=False)

    return {
        "vinfra": vinfra,
        "openstack": openstack_conn,
        "cluster_name": cluster_name,
        "nodes": nodes,
        "hosts": hosts,
        "cluster_overview": cluster_overview,
        "vstorage_stat": vstorage_stat,
        "all_interfaces": all_interfaces,
    }


def available_checks():
    return [
        "AlertsCheck",
        "TimeSyncCheck",
        "LicenseCheck",
        "KAAccessCheck",
        "InfraNodeCheck",
        "ComputeNodesCheck",
        "ComputeHealthCheck",
        "HAStateCheck",
        "OpenStackComputeAPIDNSCheck",
        "ShamanCheck",
        "TierFreeSpaceCheck",
        "StorageClusterStatusCheck",
        "MDSHealthCheck",
        "ChunkServerErrorCheck",
        "IOQueueDepthCheck",
        "ReplicaOneFilesCheck",
        "GatewayCheck",
        "NetworkBondCheck",
        "OpenStackComputeServiceCheck",
        "OpenStackVolumeServiceCheck",
        "OpenStackNetworkAgentCheck",
        "InternalBackupsCheck",
        "ExternalStorageCheck",
        "InterfaceAggregationCheck",
        "ComputeParamsCheck",
        "DisksHealthCheck",
        "NodesStorageServicesCheck",
        "ComputeClusterParams",
        "YumCheck",
        "RabbitmqClusterCheck",
        "RabbitmqQueueCheck",
        "BackendInitCheck",
        "AgentRegistrationCheck",
        "SoftwareUpdateCheck",
    ]


def available_exporters():
    return [
        "AlertsExporter",
        "NetworkBondExporter",
        "LicenseExporter",
        "DisksExporter",
        "InterfacesExporter",
        "ComputeNetworksExporter",
        "NodeExporter",
        "ExternalStorageExporter",
        "HardwareExporter",
        "InfraNetworksExporter",
        "ComputeNodeExporter",
        "ClusterOverviewExporter",
        "VstorageGetEvent",
        "VstorageStat",
        "HAExporter",
        "ComputeStoragePoliciesExporter",
        "ComputeShowExporter",
        "ComputeStatExporter",
        "EthernetsExporter",
        "StorageHardwareExporter",
        "VstorageConfig",
    ]


def build_checks(cluster_ctx, runtime_ctx):
    vinfra = cluster_ctx["vinfra"]
    openstack_conn = cluster_ctx["openstack"]
    nodes = cluster_ctx["nodes"]
    hosts = cluster_ctx["hosts"]
    cluster_name = cluster_ctx["cluster_name"]
    cluster_overview = cluster_ctx["cluster_overview"]
    vstorage_stat = cluster_ctx["vstorage_stat"]
    all_interfaces = cluster_ctx["all_interfaces"]

    return {
        "AlertsCheck": AlertsCheck(vinfra, runtime_ctx),
        "TimeSyncCheck": TimeSyncCheck(hosts, runtime_ctx),
        "LicenseCheck": LicenseCheck(vinfra, runtime_ctx),
        "KAAccessCheck": KAAccessCheck(hosts, runtime_ctx),
        "InfraNodeCheck": InfraNodeCheck(nodes, runtime_ctx),
        "ComputeNodesCheck": ComputeNodesCheck(vinfra, runtime_ctx),
        "ComputeHealthCheck": ComputeHealthCheck(vinfra, runtime_ctx),
        "HAStateCheck": HAStateCheck(vinfra, runtime_ctx),
        "OpenStackComputeAPIDNSCheck": OpenStackComputeAPIDNSCheck(openstack_conn, runtime_ctx),
        "ShamanCheck": ShamanCheck(hosts, runtime_ctx),
        "TierFreeSpaceCheck": TierFreeSpaceCheck(cluster_overview, runtime_ctx),
        "StorageClusterStatusCheck": StorageClusterStatusCheck(vinfra, cluster_overview, runtime_ctx),
        "MDSHealthCheck": MDSHealthCheck(vstorage_stat, cluster_overview, runtime_ctx),
        "ChunkServerErrorCheck": ChunkServerErrorCheck(vstorage_stat, runtime_ctx),
        "IOQueueDepthCheck": IOQueueDepthCheck(vstorage_stat, runtime_ctx),
        "ReplicaOneFilesCheck": ReplicaOneFilesCheck(cluster_name, runtime_ctx),
        "GatewayCheck": GatewayCheck(vinfra, nodes, all_interfaces, runtime_ctx),
        "NetworkBondCheck": NetworkBondCheck(hosts, runtime_ctx),
        "OpenStackComputeServiceCheck": OpenStackComputeServiceCheck(openstack_conn, runtime_ctx),
        "OpenStackVolumeServiceCheck": OpenStackVolumeServiceCheck(openstack_conn, runtime_ctx),
        "OpenStackNetworkAgentCheck": OpenStackNetworkAgentCheck(openstack_conn, runtime_ctx),
        "InternalBackupsCheck": InternalBackupsCheck(vinfra, runtime_ctx),
        "ExternalStorageCheck": ExternalStorageCheck(vinfra, runtime_ctx),
        "InterfaceAggregationCheck": InterfaceAggregationCheck(vinfra, nodes, all_interfaces, runtime_ctx),
        "ComputeParamsCheck": ComputeParamsCheck(vinfra, runtime_ctx),
        "DisksHealthCheck": DisksHealthCheck(hosts, runtime_ctx),
        "NodesStorageServicesCheck": NodesStorageServicesCheck(nodes, runtime_ctx),
        "YumCheck": YumCheck(hosts, runtime_ctx),
        "ComputeClusterParams": ComputeClusterParams(vinfra, runtime_ctx),
        "RabbitmqClusterCheck": RabbitmqClusterCheck(nodes,runtime_ctx),
        "RabbitmqQueueCheck": RabbitmqQueueCheck(runtime_ctx),
        "BackendInitCheck": BackendInitCheck(hosts, runtime_ctx),
        "AgentRegistrationCheck": AgentRegistrationCheck(hosts, runtime_ctx),
        "SoftwareUpdateCheck": SoftwareUpdateCheck(vinfra, runtime_ctx)

    }


def build_exporters(cluster_ctx, runtime_ctx):
    vinfra = cluster_ctx["vinfra"]
    nodes = cluster_ctx["nodes"]
    hosts = cluster_ctx["hosts"]
    cluster_name = cluster_ctx["cluster_name"]
    all_interfaces = cluster_ctx["all_interfaces"]

    export_dir = runtime_ctx.export_dir

    return {
        "AlertsExporter": AlertsExporter(vinfra, export_dir, runtime_ctx),
        "NetworkBondExporter": NetworkBondExporter(hosts, export_dir, runtime_ctx),
        "LicenseExporter": LicenseExporter(vinfra, export_dir, runtime_ctx),
        "DisksExporter": DisksExporter(vinfra, nodes, export_dir, runtime_ctx),
        "InterfacesExporter": InterfacesExporter(vinfra, nodes, all_interfaces, export_dir, runtime_ctx),
        "ComputeNetworksExporter": ComputeNetworksExporter(vinfra, export_dir, runtime_ctx),
        "ComputeNodeExporter": ComputeNodeExporter(vinfra, export_dir, runtime_ctx),
        "NodeExporter": NodeExporter(nodes, export_dir, runtime_ctx),
        "ExternalStorageExporter": ExternalStorageExporter(vinfra, export_dir, runtime_ctx),
        "HardwareExporter": HardwareExporter(hosts, export_dir, runtime_ctx),
        "InfraNetworksExporter": InfraNetworksExporter(vinfra, all_interfaces, export_dir, runtime_ctx),
        "ClusterOverviewExporter": ClusterOverviewExporter(vinfra, export_dir, runtime_ctx),
        "VstorageGetEvent": VstorageGetEvent(cluster_name, export_dir, runtime_ctx),
        "VstorageStat": VstorageStat(cluster_name, export_dir, runtime_ctx),
        "VstorageConfig": VstorageConfig(cluster_name, export_dir, runtime_ctx),
        "HAExporter": HAExporter(vinfra,export_dir, runtime_ctx),
        "ComputeStoragePoliciesExporter": ComputeStoragePoliciesExporter(vinfra, export_dir, runtime_ctx),
        "ComputeShowExporter": ComputeShowExporter(vinfra, export_dir, runtime_ctx),
        "ComputeStatExporter": ComputeStatExporter(vinfra, export_dir, runtime_ctx),
        "EthernetsExporter": EthernetsExporter(hosts, export_dir, runtime_ctx),
        "StorageHardwareExporter": StorageHardwareExporter(hosts, export_dir, runtime_ctx),
    }


def print_names(title, names):
    print(title)
    for name in names:
        print(f"  - {name}")


def main():
    start_time = time.time()
    args = parse_args()

    setup_logging(debug=args.debug)
    logger = logging.getLogger("main")

    if args.list:
        print_names("Available checks:", available_checks())
        return 0

    if args.listexports:
        print_names("Available exports:", available_exporters())
        return 0

    logger.info("Starting health check")

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


    ctx = HealthCheckContext(
        export_dir=EXPORT_DIR,
        no_compute=args.nocompute,
        ssh_key=args.ssh_key,
        openrc_path=args.openrc,
    )

    if not Path(args.openrc).exists():
        logger.error("OpenRC file not found: %s", args.openrc)
        sys.exit(1)

    if not Path(args.ssh_key).exists():
        logger.error("SSH key not found: %s", args.ssh_key)
        sys.exit(1)

    cluster_ctx = build_context(ctx)

    checks = build_checks(cluster_ctx, ctx)
    logger.info('Context built, cluster name: %s' % cluster_ctx["cluster_name"])

    if args.nocompute:
        checks = {
            name: check
            for name, check in checks.items()
            if name not in COMPUTE_CHECKS
        }

    print('Cluster name: %s' % cluster_ctx["cluster_name"])

    results = run_selected_checks(checks, args.check)
    print_summary(results)


    if not args.noexports:
        print(f"Export data in CSV format to {EXPORT_DIR} directory")
        exporters = build_exporters(cluster_ctx, ctx)

        if args.nocompute:
            exporters = {
                name: exporter
                for name, exporter in exporters.items()
                if name not in COMPUTE_EXPORTERS
            }
        export_errors = run_selected_exports(
            exporters,
            args.export,
        )

        if export_errors:
            print("\n=== EXPORT ERRORS ===")
            for error in export_errors:
                print(f"- {error}")

    elapsed = time.time() - start_time
    logger.info("Health check finished in %.2f seconds", elapsed)

    return 0


if __name__ == "__main__":
    sys.exit(main())