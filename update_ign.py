import base64
import json
import os
import shutil
import tarfile
import yaml
from jinja2 import Environment, FileSystemLoader


class OpenshiftOnBareMetal:

    def __init__(self):

        # Read config.yaml for CiscoACI CNI variable
        original_inventory = "config.yaml"
        with open(original_inventory, 'r') as stream:
            try:
                inventory = yaml.safe_load(stream)['all']
            except yaml.YAMLError as exc:
                print(exc)

        self.infra_vlan = str(inventory['infra_vlan'])
        self.service_vlan = str(inventory['service_vlan'])
        self.kubeapi_vlan = str(inventory['kubeapi_vlan'])
        self.node_network_mtu = str(inventory['network_interfaces']['node']['mtu'])
        self.opflex_network_mtu = str(inventory['network_interfaces']['opflex']['mtu'])
        self.cp_node_network_interface = list(inventory['os_cp_nodes']['node_network_interface'])
        self.cp_aci_infra_network_interface = list(inventory['os_cp_nodes']['aci_infra_network_interface'])
        self.compute_node_network_interface = list(inventory['os_compute_nodes']['node_network_interface'])
        self.compute_aci_infra_network_interface = list(inventory['os_compute_nodes']['aci_infra_network_interface'])


    def create_bond(self, bond_name, mtu):

        ifcfg_bond0 = ("""NAME=""" + bond_name +"""
            DEVICE=""" + bond_name + """
            ONBOOT=yes
            NETBOOT=yes
            BOOTPROTO=dhcp
            BONDING_MASTER=yes
            BONDING_OPTS="mode=4 miimon=100 lacp_rate=1"
            NAME=""" + bond_name + """
            TYPE=Bond
            MTU=""" + mtu + """
            """).encode()
        return ifcfg_bond0


    def create_slave_interface(self, interface_name, bond_name, mtu):

        interface = ("""NAME=""" + interface_name +"""
            TYPE=Ethernet
            ONBOOT=yes
            NETBOOT=yes
            SLAVE=yes
            MASTER="""+bond_name+"""
            DEVICE=""" + interface_name +"""
            MTU=""" + mtu + """
            """).encode()
        return interface


    def create_interface(self, interface_name, mtu):
        interface = ("""NAME=""" + interface_name +"""
            TYPE=Ethernet
            ONBOOT=yes
            NETBOOT=yes
            DEVICE=""" + interface_name +"""
            MTU=""" + mtu + """
            """).encode()
        return interface


    def create_opflex_connection_without_bond(self, config_data, aci_infra_network_interface):

        opflex_conn = ("""VLAN=yes
            TYPE=Vlan
            VLAN_ID=""" + self.infra_vlan + """
            REORDER_HDR=yes
            GVRP=no
            MVRP=no
            PROXY_METHOD=none
            BROWSER_ONLY=no
            BOOTPROTO=dhcp
            DEFROUTE=yes
            IPV4_FAILURE_FATAL=no
            IPV6INIT=no
            NAME=opflex-conn
            DEVICE=""" + aci_infra_network_interface +"."+ self.infra_vlan + """
            ONBOOT=yes
            MTU=""" + self.opflex_network_mtu + """
            """).encode()
        ifcfg_opflex_conn_b64 = base64.standard_b64encode(opflex_conn).decode().strip()
        config_data['ifcfg_opflex_conn'] = {'base64': ifcfg_opflex_conn_b64, 'path': '/etc/sysconfig/network-scripts/ifcfg-opflex-conn'}
        route_opflex_conn = """ADDRESS0=224.0.0.0
        NETMASK0=240.0.0.0
        METRIC0=1000
        """.encode()
        route_opflex_conn_b64 = base64.standard_b64encode(route_opflex_conn).decode().strip()
        config_data['route_opflex_conn'] = {'base64': route_opflex_conn_b64, 'path': '/etc/sysconfig/network-scripts/route-opflex-conn'}


    def create_opflex_connection_with_bond(self, bond_name, config_data):

        opflex_conn = ("""VLAN=yes
            TYPE=Vlan
            PHYSDEV=""" +bond_name + """
            VLAN_ID=""" + self.infra_vlan + """
            REORDER_HDR=yes
            GVRP=no
            MVRP=no
            PROXY_METHOD=none
            BROWSER_ONLY=no
            BOOTPROTO=dhcp
            DEFROUTE=yes
            IPV4_FAILURE_FATAL=no
            IPV6INIT=no
            NAME=opflex-conn
            DEVICE=""" + bond_name +"."+ self.infra_vlan + """
            ONBOOT=yes
            MTU=""" + self.opflex_network_mtu + """
            """).encode()

        ifcfg_opflex_conn_b64 = base64.standard_b64encode(opflex_conn).decode().strip()
        config_data['ifcfg_opflex_conn'] = {'base64': ifcfg_opflex_conn_b64, 'path': '/etc/sysconfig/network-scripts/ifcfg-opflex-conn'}
        route_opflex_conn = """ADDRESS0=224.0.0.0
        NETMASK0=240.0.0.0
        METRIC0=1000
        """.encode()
        route_opflex_conn_b64 = base64.standard_b64encode(route_opflex_conn).decode().strip()
        config_data['route_opflex_conn'] = {'base64': route_opflex_conn_b64, 'path': '/etc/sysconfig/network-scripts/route-opflex-conn'}


    def update(self, ignition, node_type, choice):

        if node_type == "master":
            aci_infra_network_interface = self.cp_aci_infra_network_interface
            node_network_interface = self.cp_node_network_interface
        else:
            aci_infra_network_interface = self.compute_aci_infra_network_interface
            node_network_interface = self.compute_node_network_interface          

        config_data = {}
        if choice == 1:

            """ Single interface for node network and bond interface for infra network """
            ifcfg_bond0 = self.create_bond("bond0", self.opflex_network_mtu)
            ifcfg_bond0_b64 = base64.standard_b64encode(ifcfg_bond0).decode().strip()
            config_data['ifcfg_bond0'] = {'base64': ifcfg_bond0_b64, 'path': '/etc/sysconfig/network-scripts/ifcfg-bond0'}

            interface_name = "ifcfg-" + aci_infra_network_interface[0]
            infra_network_interface1 = self.create_slave_interface(aci_infra_network_interface[0], "bond0", self.opflex_network_mtu)
            infra_network_interface1_b64 = base64.standard_b64encode(infra_network_interface1).decode().strip()
            config_data[interface_name] = {'base64': infra_network_interface1_b64, 'path': '/etc/sysconfig/network-scripts/'+ interface_name}

            interface_name = "ifcfg-" + aci_infra_network_interface[1]
            infra_network_interface2 = self.create_slave_interface(aci_infra_network_interface[1], "bond0", self.opflex_network_mtu)
            infra_network_interface2_b64 = base64.standard_b64encode(infra_network_interface2).decode().strip()
            config_data[interface_name] = {'base64': infra_network_interface2_b64, 'path': '/etc/sysconfig/network-scripts/' +  interface_name}

            self.create_opflex_connection_with_bond("bond0", config_data)

        elif choice == 2:
            """  Bond interface for both node and infra networks """

            ifcfg_bond0 = self.create_bond("bond0", self.node_network_mtu)
            ifcfg_bond0_b64 = base64.standard_b64encode(ifcfg_bond0).decode().strip()
            config_data['ifcfg_bond0'] = {'base64': ifcfg_bond0_b64, 'path': '/etc/sysconfig/network-scripts/ifcfg-bond0'}

            interface_name = "ifcfg-" + node_network_interface[0]
            node_network_interface1 = self.create_slave_interface(node_network_interface[0], "bond0", self.node_network_mtu)
            node_network_interface1_b64 = base64.standard_b64encode(node_network_interface1).decode().strip()
            config_data[interface_name] = {'base64': node_network_interface1_b64, 'path': '/etc/sysconfig/network-scripts/' + interface_name}

            interface_name = "ifcfg-" + node_network_interface[1] 
            node_network_interface2 = self.create_slave_interface(node_network_interface[1], "bond0", self.node_network_mtu)
            node_network_interface2_b64 = base64.standard_b64encode(node_network_interface2).decode().strip()
            config_data[interface_name] = {'base64': node_network_interface2_b64, 'path': '/etc/sysconfig/network-scripts/' + interface_name}
 
            ifcfg_bond1 = self.create_bond("bond1", self.opflex_network_mtu)
            ifcfg_bond1_b64 = base64.standard_b64encode(ifcfg_bond1).decode().strip()
            config_data['ifcfg_bond1'] = {'base64': ifcfg_bond1_b64, 'path': '/etc/sysconfig/network-scripts/ifcfg-bond1'}

            interface_name = "ifcfg-" + aci_infra_network_interface[0]
            infra_network_interface1 = self.create_slave_interface(aci_infra_network_interface[0], "bond1", self.opflex_network_mtu)
            infra_network_interface1_b64 = base64.standard_b64encode(infra_network_interface1).decode().strip()
            config_data[interface_name] = {'base64': infra_network_interface1_b64, 'path': '/etc/sysconfig/network-scripts/'  + interface_name}
             
            interface_name = "ifcfg-" + aci_infra_network_interface[1]
            infra_network_interface2 = self.create_slave_interface(aci_infra_network_interface[1], "bond1", self.opflex_network_mtu)
            infra_network_interface2_b64 = base64.standard_b64encode(infra_network_interface2).decode().strip()
            config_data[interface_name] = {'base64': infra_network_interface2_b64, 'path': '/etc/sysconfig/network-scripts/' + interface_name}

            self.create_opflex_connection_with_bond("bond1", config_data)

        elif choice == 3:
            """ Bond interface for node network and single interface for infra network"""
            
            ifcfg_bond0 = self.create_bond("bond0", self.node_network_mtu)
            ifcfg_bond0_b64 = base64.standard_b64encode(ifcfg_bond0).decode().strip()
            config_data['ifcfg_bond0'] = {'base64': ifcfg_bond0_b64, 'path': '/etc/sysconfig/network-scripts/ifcfg-bond0'}

            interface_name = "ifcfg-" + node_network_interface[0]
            node_network_interface1 = self.create_slave_interface(node_network_interface[0], "bond0", self.node_network_mtu)
            node_network_interface1_b64 = base64.standard_b64encode(node_network_interface1).decode().strip()
            config_data[interface_name] = {'base64': node_network_interface1_b64, 'path': '/etc/sysconfig/network-scripts/' + interface_name}
            
            interface_name = "ifcfg-" + node_network_interface[1]
            node_network_interface2 = self.create_slave_interface(node_network_interface[1], "bond0", self.node_network_mtu)
            node_network_interface2_b64 = base64.standard_b64encode(node_network_interface2).decode().strip()
            config_data[interface_name] = {'base64': node_network_interface2_b64, 'path': '/etc/sysconfig/network-scripts/' + interface_name}

            interface_name = "ifcfg-" + aci_infra_network_interface[0]
            infra_network_interface1 = self.create_interface(aci_infra_network_interface[0], self.opflex_network_mtu)
            infra_network_interface1_b64 = base64.standard_b64encode(infra_network_interface1).decode().strip()
            config_data[interface_name] = {'base64': infra_network_interface1_b64, 'path': '/etc/sysconfig/network-scripts/' + interface_name}

            self.create_opflex_connection_without_bond(config_data, aci_infra_network_interface[0])
        
        else:
            """single interface for both node and infra networks"""

            interface_name = "ifcfg-" + aci_infra_network_interface[0]
            infra_network_interface1 = self.create_interface(aci_infra_network_interface[0], self.opflex_network_mtu)
            infra_network_interface1_b64 = base64.standard_b64encode(infra_network_interface1).decode().strip()
            config_data[interface_name] = {'base64': infra_network_interface1_b64, 'path': '/etc/sysconfig/network-scripts/'+ interface_name}
            
            self.create_opflex_connection_without_bond(config_data, aci_infra_network_interface[0])


        if 'storage' not in ignition.keys():
            ignition['storage'] = {}
        files = ignition['storage'].get('files', [])

        if "bootstrap" not in node_type:

            for interface, interface_config in config_data.items():
                files.append(
                    {
                    'path': interface_config['path'],
                    'mode': 420,
                    'contents': {
                    'source': 'data:text/plain;charset=utf-8;base64,' + interface_config['base64'],
                    'verification': {}
                    },
                    'filesystem': 'root',
                })


        ignition['storage']['files'] = files
        return ignition


if __name__ == "__main__":
    print("""
        1.Single interface for node network and bond interface for infra network
        2.Bond interface for both node and infra networks
        3.Bond interface for node network and single interface for infra network
        4.Single interface for both node and infra networks
        """)
    ans=input("Which option would you like to choose? ")
    if ans=="1":
        choice = 1
    elif ans=="2":
        choice = 2
    elif ans == "3":
        choice = 3
    elif ans == "4":
        choice = 4
    else:
        print("\n   Invalid Option, Please Try Again")


    infra_id = os.environ.get('INFRA_ID', 'openshift').encode()

    openshiftOnBaremetal = OpenshiftOnBareMetal()

    with open('bootstrap.ign', 'r') as f:
        ignition = json.load(f)
    ignition = openshiftOnBaremetal.update(ignition, "bootstrap", choice)
    with open('bootstrap.ign', 'w') as f:
        json.dump(ignition, f)

    with open('master.ign', 'r') as f:
        ignition = json.load(f)
    ignition = openshiftOnBaremetal.update(ignition, "master", choice)
    with open(infra_id.decode() + '-master-ignition.json', 'w') as f:
        json.dump(ignition, f)

    with open('worker.ign', 'r') as f:
        ignition = json.load(f)
    ignition = openshiftOnBaremetal.update(ignition, "worker", choice)
    with open(infra_id.decode() + '-worker-ignition.json', 'w') as f:
        json.dump(ignition, f)
