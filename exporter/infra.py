from .base import CSVExporter



class InterfacesExporter(CSVExporter):
    """
    Exports node interfaces exactly as original script:
    vinfra node iface list -a --long
    """
    filename = "interfaces.csv"

    def __init__(self, vinfra, nodes, all_interfaces, export_dir,ctx):
        super().__init__(export_dir,ctx)
        self.vinfra = vinfra
        self.nodes = nodes
        self.all_interfaces = all_interfaces
        self.node_map = {
            n["id"]: n["host"]
            for n in self.nodes
        }
    def collect(self):
        interfaces = self.all_interfaces
        networks = self.vinfra.run("cluster", "network", "list")
        network_map = {n["id"]: n["name"] for n in networks}
        headers = ['name', 'server', 'ipv4', 'state', 'network', 'mtu', 'speed', 'gw4']
        rows = []

        for iface in interfaces:
            host = self.node_map.get(iface.get("node_id"), iface.get("node_id"))
            network = network_map.get(iface.get("network"))
            rows.append([
                iface.get("name"),
                host,
                iface.get("ipv4"),
                iface.get("state"),
                network,
                iface.get("mtu"),
                iface.get("speeds",{}).get("current"),
                iface.get("gw4"),
            ])

        self.write(headers, rows)


class NodeExporter(CSVExporter):
    filename = "nodes.csv"
    def __init__(self, nodes, export_dir,ctx):
        super().__init__(export_dir,ctx)
        self.nodes = nodes

    def collect(self):
        headers = ['id', 'host', 'is_primary', 'is_online', 'is_assigned', 'is_in_ha', 'roles']
        rows = []
        for node in self.nodes:
            roles = list(node.get('roles',{}).keys())
            roles.sort()
            rows.append([
                node.get("id"),
                node.get("host"),
                node.get("is_primary"),
                node.get("is_online"),
                node.get("is_assigned"),
                node.get("is_in_ha"),
                '-'.join(roles)
            ])

        self.write(headers, rows)


class InfraNetworksExporter(CSVExporter):

    filename = "infranets.csv"

    def __init__(self, vinfra, all_interfaces, export_dir,ctx):
        super().__init__(export_dir,ctx)
        self.vinfra = vinfra
        self.all_interfaces = all_interfaces
    def collect(self):
        headers = ['name', 'CIDR', 'interfaces', 'VLAN', 'traffic_types']
        networks = self.vinfra.run("cluster", "network", "list", "--long")
        all_interfaces = self.all_interfaces
        iface_map = dict()
        for iface in all_interfaces:
            net_id = iface.get('network')
            if net_id:
                iface_map.setdefault(net_id, set()).add(iface.get('name'))
        rows = []
        for network in networks:
            net_id = network['id']
            subnets = network.get('encryption', {}).get('subnets') or []
            cidr = subnets[0].get('cidr') if subnets else ''
            traffic = ' '.join(network.get('traffic_types', []))
            binds = iface_map.get(net_id, set())
            interfaces = ', '.join(sorted(binds)) if binds else ''

            rows.append([network['name'], cidr, interfaces, network['vlan'], traffic])
        self.write(headers, rows)

