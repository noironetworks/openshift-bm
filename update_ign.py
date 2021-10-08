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
# Network interfaces: This script assumes that each node has three interfaces -
#                     - one for node Network
#                     - the second and third in bonded configuration for the ACI Infra Network (the pod traffic also goes over this) 
#                     If the nodes have only two network inferfaces, then there can be no bonding. Similarly, if the node
#                     has four or more interfaces then you can choose to have bonded pairs for both the node and infra networks.
#                     In either of those cases this script will have to be modified to account for those differences.

# How to run this script: python3 update_ign.py

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



# Read config.yaml for CiscoACI CNI variable
original_inventory = "config.yaml"
with open(original_inventory, 'r') as stream:
    try:
        inventory = yaml.safe_load(stream)['all']
    except yaml.YAMLError as exc:
        print(exc)

infra_vlan = str(inventory['infra_vlan'])
service_vlan = str(inventory['service_vlan'])
kubeapi_vlan = str(inventory['kubeapi_vlan'])
master_count = inventory['os_cp_nodes_number']
worker_count = inventory['os_compute_nodes_number']
node_network_mtu = str(inventory['network_interfaces']['node']['mtu'])
opflex_network_mtu = str(inventory['network_interfaces']['opflex']['mtu'])

def update(hostname,ignition):

    config_data = {}

    ifcfg_bond0 = ("""NAME="bond0"
DEVICE="bond0"
ONBOOT=yes
NETBOOT=yes
BOOTPROTO=none
BONDING_MASTER=yes
BONDING_OPTS="mode=4 miimon=100 lacp_rate=1"
NAME="bond0"
TYPE=Bond
MTU=""" + opflex_network_mtu + """
""").encode()

    ifcfg_bond0_b64 = base64.standard_b64encode(ifcfg_bond0).decode().strip()

    config_data['ifcfg_bond0'] = {'base64': ifcfg_bond0_b64, 'path': '/etc/sysconfig/network-scripts/ifcfg-bond0'}

    ifcfg_ens4 = ("""NAME="ens4"
TYPE=Ethernet
ONBOOT=yes
NETBOOT=yes
SLAVE=yes
MASTER="bond0"
DEVICE="ens4"
MTU=""" + opflex_network_mtu + """
""").encode()

    ifcfg_ens4_b64 = base64.standard_b64encode(ifcfg_ens4).decode().strip()

    config_data['ifcfg_ens4'] = {'base64': ifcfg_ens4_b64, 'path': '/etc/sysconfig/network-scripts/ifcfg-ens4'}

    ifcfg_ens5 = ("""NAME="ens5"
TYPE=Ethernet
ONBOOT=yes
NETBOOT=yes
SLAVE=yes
MASTER="bond0"
DEVICE="ens5"
MTU=""" + opflex_network_mtu + """
""").encode()

    ifcfg_ens5_b64 = base64.standard_b64encode(ifcfg_ens5).decode().strip()

    config_data['ifcfg_ens5'] = {'base64': ifcfg_ens5_b64, 'path': '/etc/sysconfig/network-scripts/ifcfg-ens5'}

    opflex_conn = ("""VLAN=yes
TYPE=Vlan
PHYSDEV=bond0
VLAN_ID=""" + infra_vlan + """
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
DEVICE=""" + """bond0.""" + infra_vlan + """
ONBOOT=yes
MTU=""" + opflex_network_mtu + """
""").encode()

    ifcfg_opflex_conn_b64 = base64.standard_b64encode(opflex_conn).decode().strip()

    config_data['ifcfg_opflex_conn'] = {'base64': ifcfg_opflex_conn_b64, 'path': '/etc/sysconfig/network-scripts/ifcfg-opflex-conn'}

    route_opflex_conn = """ADDRESS0=224.0.0.0
NETMASK0=240.0.0.0
METRIC0=1000
""".encode()

    route_opflex_conn_b64 = base64.standard_b64encode(route_opflex_conn).decode().strip()

    config_data['route_opflex_conn'] = {'base64': route_opflex_conn_b64, 'path': '/etc/sysconfig/network-scripts/route-opflex-conn'}
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

         files.append(
             {
                 'path': config_data['ifcfg_bond0']['path'],
                 'mode': 420,
                 'contents': {
                     'source': 'data:text/plain;charset=utf-8;base64,' + config_data['ifcfg_bond0']['base64'],
                     'verification': {}
                 },
                 'filesystem': 'root',
             })


         files.append(
             {
                 'path': config_data['ifcfg_ens4']['path'],
                 'mode': 420,
                 'contents': {
                     'source': 'data:text/plain;charset=utf-8;base64,' + config_data['ifcfg_ens4']['base64'],
                     'verification': {}
                 },
                 'filesystem': 'root',
             })

         files.append(
             {
                 'path': config_data['ifcfg_ens5']['path'],
                 'mode': 420,
                 'contents': {
                     'source': 'data:text/plain;charset=utf-8;base64,' + config_data['ifcfg_ens5']['base64'],
                     'verification': {}
                 },
                 'filesystem': 'root',
             })

         files.append(
             {
                 'path': config_data['ifcfg_opflex_conn']['path'],
                 'mode': 420,
                 'contents': {
                     'source': 'data:text/plain;charset=utf-8;base64,' + config_data['ifcfg_opflex_conn']['base64'],
                     'verification': {}
                 },
                 'filesystem': 'root',
             })

         files.append(
             {
                 'path': config_data['route_opflex_conn']['path'],
                 'mode': 420,
                 'contents': {
                     'source': 'data:text/plain;charset=utf-8;base64,' + config_data['route_opflex_conn']['base64'],
                     'verification': {}
                 },
                 'filesystem': 'root',
             })

    ignition['storage']['files'] = files
    return ignition


infra_id = os.environ.get('INFRA_ID', 'openshift').encode()

with open('bootstrap.ign', 'r') as f:
    ignition = json.load(f)
bootstrap_hostname = infra_id + b'-bootstrap\n'
ignition = update(bootstrap_hostname,ignition)
with open('bootstrap.ign', 'w') as f:
    json.dump(ignition, f)

for index in range(0,master_count):
    master_hostname = infra_id + b'-master-' + str(index).encode() + b'\n'
    with open('master.ign', 'r') as f:
        ignition = json.load(f)
    ignition = update(master_hostname,ignition)
    with open(infra_id.decode() + '-master-' + str(index) + '-ignition.json', 'w') as f:
        json.dump(ignition, f)

for index in range(0,worker_count):
    master_hostname = infra_id + b'-worker-' + str(index).encode() + b'\n'
    with open('worker.ign', 'r') as f:
        ignition = json.load(f)
    ignition = update(master_hostname,ignition)
    with open(infra_id.decode() + '-worker-' + str(index) + '-ignition.json', 'w') as f:
        json.dump(ignition, f)


