# This script is based on the information provided here:
# https://github.com/openshift/installer/blob/release-4.7/docs/user/openstack/install_upi.md
#
# Before running this script please update the config.yaml in this directory

# This script does the following:
#  Inserts hostname into the boostrap.ign
#  Creates the ignition files for each master and worker node, and inserts the hostname and network-scripts into those

# Assumptions:
# Interface names in RHCOS-4.x based nodes have the inteface naming convention: ens2, ens4, ens5
#
# Hostnames are assigned by this script using the convention: <Infra-Id>-<bootstrap|master|worker>-<Number>
#
# Ignition file names follow the convention:  <Infra-Id>-bootstrap|master|worker-<index>-ignition.json 
#
# Network interfaces:  We will have following option to choose from 
#                       1.Single interface for node network and bond interface for infra network
#                       2.Bond interface for both node and infra networks
#                       3.Bond interface for node network and single interface for infra network
#                       4.Single interface for both node and infra networks
#
#
#               
#               Please update the config.yaml as follows:
#                    case 1: Please provide single node network interface name  and two aci infra network interface name in config.yaml file
#                    case 2: Please provide two node network interface name  and two aci infra network interface name in config.yaml file
#                    case 3: Please provide two node network interface name  and single aci infra network interface name in config.yaml file
#                    case 4: Please provide single node network interface name  and single aci infra network interface name in config.yaml file



# How to run this script: python3 update_ign.py
#          
# Expected Output: Igniton files for each of the nodes including the bootstrap with the names: <Infra-Id>-bootstrap|master|worker-<index>-ignition.json

# What to do after running this script: Copy the generated ignition files to directory where they will be served from at install time, and proceed with
# the installation.

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
        self.master_count = inventory['os_cp_nodes_number']
        self.worker_count = inventory['os_compute_nodes_number']
        self.node_network_mtu = str(inventory['network_interfaces']['node']['mtu'])
        self.opflex_network_mtu = str(inventory['network_interfaces']['opflex']['mtu'])
        self.node_network_interface = list(inventory["node_network_interface"])
        self.aci_infra_network_interface = list(inventory["aci_infra_network_interface"])


    def create_bond(self, bond_name, mtu):

        ifcfg_bond0 = ("""NAME=""" + bond_name +"""
            DEVICE=""" + bond_name + """
            ONBOOT=yes
            NETBOOT=yes
            BOOTPROTO=none
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

    def create_opflex_connection_without_bond(self, config_data):

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
            DEVICE= """ + self.aci_infra_network_interface[0] +"."+ self.infra_vlan + """
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


    def update(self, hostname,ignition, choice):

        config_data = {}
        if choice == 1:

            """ Single interface for node network and bond interface for infra network """
            ifcfg_bond0 = self.create_bond("bond0", self.opflex_network_mtu)
            ifcfg_bond0_b64 = base64.standard_b64encode(ifcfg_bond0).decode().strip()
            config_data['ifcfg_bond0'] = {'base64': ifcfg_bond0_b64, 'path': '/etc/sysconfig/network-scripts/ifcfg-bond0'}


            interface_name = "ifcfg-" + self.aci_infra_network_interface[0]
            infra_network_interface1 = self.create_slave_interface(self.aci_infra_network_interface[0], "bond0", self.opflex_network_mtu)
            infra_network_interface1_b64 = base64.standard_b64encode(infra_network_interface1).decode().strip()
            config_data[interface_name] = {'base64': infra_network_interface1_b64, 'path': '/etc/sysconfig/network-scripts/'+ interface_name}

            interface_name = "ifcfg-" + self.aci_infra_network_interface[1]
            infra_network_interface2 = self.create_slave_interface(self.aci_infra_network_interface[1], "bond0", self.opflex_network_mtu)
            infra_network_interface2_b64 = base64.standard_b64encode(infra_network_interface2).decode().strip()
            config_data[interface_name] = {'base64': infra_network_interface2_b64, 'path': '/etc/sysconfig/network-scripts/' +  interface_name}

            self.create_opflex_connection_with_bond("bond0", config_data)

        elif choice == 2:
            """  Bond interface for both node and infra networks """

            ifcfg_bond0 = self.create_bond("bond0", self.node_network_mtu)
            ifcfg_bond0_b64 = base64.standard_b64encode(ifcfg_bond0).decode().strip()
            config_data['ifcfg_bond0'] = {'base64': ifcfg_bond0_b64, 'path': '/etc/sysconfig/network-scripts/ifcfg-bond0'}

            interface_name = "ifcfg-" + self.node_network_interface[0]
            node_network_interface1 = self.create_slave_interface(self.node_network_interface[0], "bond0", self.node_network_mtu)
            node_network_interface1_b64 = base64.standard_b64encode(node_network_interface1).decode().strip()
            config_data[interface_name] = {'base64': node_network_interface1_b64, 'path': '/etc/sysconfig/network-scripts/' + interface_name}

            interface_name = "ifcfg-" + self.node_network_interface[1]
             
            node_network_interface2 = self.create_slave_interface(self.node_network_interface[1], "bond0", self.node_network_mtu)
            node_network_interface2_b64 = base64.standard_b64encode(node_network_interface2).decode().strip()
            config_data[interface_name] = {'base64': node_network_interface2_b64, 'path': '/etc/sysconfig/network-scripts/' + interface_name}


            ifcfg_bond1 = self.create_bond("bond1", self.opflex_network_mtu)
            ifcfg_bond1_b64 = base64.standard_b64encode(ifcfg_bond1).decode().strip()
            config_data['ifcfg_bond1'] = {'base64': ifcfg_bond1_b64, 'path': '/etc/sysconfig/network-scripts/ifcfg-bond1'}

            interface_name = "ifcfg-" + self.aci_infra_network_interface[0]
            infra_network_interface1 = self.create_slave_interface(self.aci_infra_network_interface[0], "bond1", self.opflex_network_mtu)
            infra_network_interface1_b64 = base64.standard_b64encode(infra_network_interface1).decode().strip()
            config_data[interface_name] = {'base64': infra_network_interface1_b64, 'path': '/etc/sysconfig/network-scripts/'  + interface_name}
             
            interface_name = "ifcfg-" + self.aci_infra_network_interface[1]

            infra_network_interface2 = self.create_slave_interface(self.aci_infra_network_interface[1], "bond1", self.opflex_network_mtu)
            infra_network_interface2_b64 = base64.standard_b64encode(infra_network_interface2).decode().strip()
            config_data[interface_name] = {'base64': infra_network_interface2_b64, 'path': '/etc/sysconfig/network-scripts/' + interface_name}

            self.create_opflex_connection_with_bond("bond1", config_data)

        elif choice == 3:

            """ Bond interface for node network and single interface for infra network"""
            
            ifcfg_bond0 = self.create_bond("bond0", self.node_network_mtu)
            ifcfg_bond0_b64 = base64.standard_b64encode(ifcfg_bond0).decode().strip()
            config_data['ifcfg_bond0'] = {'base64': ifcfg_bond0_b64, 'path': '/etc/sysconfig/network-scripts/ifcfg-bond0'}

            interface_name = "ifcfg-" + self.node_network_interface[0]

            node_network_interface1 = self.create_slave_interface(self.node_network_interface[0], "bond0", self.node_network_mtu)
            node_network_interface1_b64 = base64.standard_b64encode(node_network_interface1).decode().strip()
            config_data[interface_name] = {'base64': node_network_interface1_b64, 'path': '/etc/sysconfig/network-scripts/' + interface_name}
            
            interface_name = "ifcfg-" + self.node_network_interface[1]
            node_network_interface2 = self.create_slave_interface(self.node_network_interface[1], "bond0", self.node_network_mtu)
            node_network_interface2_b64 = base64.standard_b64encode(node_network_interface2).decode().strip()
            config_data[interface_name] = {'base64': node_network_interface2_b64, 'path': '/etc/sysconfig/network-scripts/' + interface_name}

            interface_name = "ifcfg-" + self.aci_infra_network_interface[0]
            infra_network_interface1 = self.create_interface(self.aci_infra_network_interface[0], self.opflex_network_mtu)
            infra_network_interface1_b64 = base64.standard_b64encode(infra_network_interface1).decode().strip()
            config_data[interface_name] = {'base64': infra_network_interface1_b64, 'path': '/etc/sysconfig/network-scripts/' + interface_name}

            self.create_opflex_connection_without_bond(config_data)
        else:
            """single interface for both node and infra networks"""

            interface_name = "ifcfg-" + self.aci_infra_network_interface[0]
            infra_network_interface1 = self.create_interface(self.aci_infra_network_interface[0], self.opflex_network_mtu)
            infra_network_interface1_b64 = base64.standard_b64encode(infra_network_interface1).decode().strip()
            config_data[interface_name] = {'base64': infra_network_interface1_b64, 'path': '/etc/sysconfig/network-scripts/'+ interface_name}
            self.create_opflex_connection_without_bond(config_data)

        if 'storage' not in ignition.keys():
            ignition['storage'] = {}
        files = ignition['storage'].get('files', [])
        hostname_b64 = base64.standard_b64encode(hostname).decode().strip()
        files.append(
            {
                'path': '/etc/hostname',
                'mode': 420,
                'contents': {
                    'source': 'data:text/plain;charset=utf-8;base64,' + hostname_b64,
                    'verification': {}
                },
                'filesystem': 'root',
            })

        if 'bootstrap' not in hostname.decode():

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
    bootstrap_hostname = infra_id + b'-bootstrap\n'
    ignition = openshiftOnBaremetal.update(bootstrap_hostname,ignition, choice)
    with open('bootstrap.ign', 'w') as f:
        json.dump(ignition, f)

    for index in range(0, openshiftOnBaremetal.master_count):
        master_hostname = infra_id + b'-master-' + str(index).encode() + b'\n'
        with open('master.ign', 'r') as f:
            ignition = json.load(f)
        ignition = openshiftOnBaremetal.update(master_hostname,ignition, choice)
        with open(infra_id.decode() + '-master-' + str(index) + '-ignition.json', 'w') as f:
            json.dump(ignition, f)

    for index in range(0, openshiftOnBaremetal.worker_count):
        master_hostname = infra_id + b'-worker-' + str(index).encode() + b'\n'
        with open('worker.ign', 'r') as f:
            ignition = json.load(f)
        ignition = openshiftOnBaremetal.update(master_hostname,ignition, choice)
        with open(infra_id.decode() + '-worker-' + str(index) + '-ignition.json', 'w') as f:
            json.dump(ignition, f)