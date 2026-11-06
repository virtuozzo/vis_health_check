# Virtuozzo Infrastructure Health Check Tool

```

usage: main.py [-h] [-c CHECK] [-l] [-n] [--listexports] [-e EXPORT] [--debug] [--nocompute] [--ssh-key SSH_KEY]
               [--openrc OPENRC]


optional arguments:
  -h, --help            show this help message and exit
  -c CHECK, --check CHECK
                        Run only specific check, for example: LicenseCheck
  -l, --list            List available checks
  -n, --noexports       Do not export data
  --listexports         List available exports
  -e EXPORT, --export EXPORT
                        Execute only specific exporter
  --debug               Enable debug logging
  --nocompute           Run in infrastructure/storage-only mode without Compute checks and exports
  --ssh-key SSH_KEY     SSH private key path (default: /etc/kolla/id_rsa)
  --openrc OPENRC       OpenStack openrc file (default: /etc/kolla/admin-openrc.sh)

```


# Checks
| Check                                                                           | Expectations                                                                                                         |
|---------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------|
| time_sync                                                                       | All nodes in the cluster should be configured in ETC/UTC time zone and synchronized with NTP servers                 |
| license, access_to_ka                                                           | License status, connectivity to license server                                                                       |
| infra_nodes, compute_nodes, compute_status                                      | All storage & Compute nodes are in Healthy status                                                                    |
| ha_state                                                                        | 5 out of 5 nodes are added to the management HA configuration as recommended                                         |
| openstack_compute_dns                                                           | OpenStack API endpoint names are configured using public DNS configuration                                           |
| shaman_check                                                                    | All nodes should have the shaman service up and running across the cluster                                           |
| tier_free_space                                                                 | The cluster should have less than 85% storage consumption. Storage failure domains quantity.                         |
| storage_cluster_status                                                          | Storage Cluster Status                                                                                               |
| mds_health                                                                      | MDS CPU and disk Usage : There’s no high CPU or disk usage, and cluster should have 5 MDS                            |
| io_queue_depth                                                                  | IOQDEPTH : There are no present high levels of I/O queue depth                                                       |
| chunk_server_errors                                                             | Chunk Server Error: There are no recent errors (events and LAST)                                                     |
| replica_one_files                                                               | No unique chunks                                                                                                     |
| gateways                                                                        | Gateway is consistent across all nodes                                                                               |
| network_bonds                                                                   | The cluster is configured with two BOND interfaces consists of 2 ports each. Transmit Hash algorithm set to Layer3+4 |
| openstack_compute_services, openstack_volume_services, openstack_network_agents | OpenStack services are in running state                                                                              |
| internal_backups                                                                | Validate if the customer has backups configured in the cluster                                                       |
| external_storage                                                                | External Storage status                                                                                              |
| interface_bonds                                                                 | Interfaces aggregation for infrastructure networks                                                                   |
| compute_params                                                                  | Custom compute service parameters                                                                                    |
| disk_health                                                                     | Storage disks health and status                                                                                      |
| nodes_storage_services                                                          | Storage services check                                                                                               |
| compute_cluster_params                                                          | Show cluster addons and parameters                                                                                   |
| yum_repos_check                                                                 | Show if hci yum repositores are enabled and no external are configured                                               |
| rabbitmq_cluster                                                                | Check RabbitMQ cluster status and alingment on management nodes                                                      |
| rabbitmq_queues                                                                 | Check RabbitMQ queues status and statistics                                                                          |
| backendinit_check                                                               | Not initialized backends in cluster                                                                                  |
| agent_registration_check                                                        | Agent registration is not finished                                                                                   | 
| software_update_state                                                           | Versions from software-updates status                                                                                |
# Exports

Directory: exports

| File                         | Exporter                       | Description                                                         |
|------------------------------|--------------------------------|---------------------------------------------------------------------|
| alerts.csv                   | AlertsExporter                 | Alerts with severity error and warning for further review           |
| all_disks.csv                | DisksExporter                  | All disks with corresponding roles                                  |
| cses.csv                     | DisksExporter                  | CS disks to check proper alignment and settings and characteristics |
| caches.csv                   | DisksExporter                  | SSD cache, might be empty                                           |
| md.csv                       | DisksExporter                  | Software raid members, might be empty                               |
| compute_networks.csv         | ComputeNetworksExporter        | Compute physical networks                                           |
| interfaces.csv               | InterfacesExporter             | Check network settings, including MTU                               |
| license.csv                  | LicenseExporter                | Information about installed license key                             |
| external_storage.csv         | ExternalStorageExporter        | External storage volume driver and status                           |
| hardware.csv                 | HardwareExporter               | Information about servers, RAM and CPUs                             | 
| infranets.csv                | InfraNetworksExporter          | Infrastructructure Networks                                         |
| compute_nodes.csv            | ComputeNodeExporter            | List of compute nodes with roles                                    |
| cluster_overview.json        | ClusterOverviewExporter        | Cluster general Overview                                            |
| vstorage_get-event.txt       | VstorageGetEvent               | Event log of storage cluster                                        |
| ha.json                      | HAExporter                     | Information about High Availability                                 |
| compute_storage_policies.csv | ComputeStoragePoliciesExporter | Information about compute storage policies                          |
| compute_show.json            | ComputeShowExporter            | Compute cluster information summary                                 |                              
| compute_stat.json            | ComputeStatExporter            | Compute cluster statistics                                          | 
| bonds.csv                    | NetworkBondExporter            | Information about bonds                                             |
| ethernets.csv                | EthernetsExporter              | Ethernet hardware information                                       |
| storage_hardware.json        | StorageHardwareExporter        | Storage subsystem                                                   |
