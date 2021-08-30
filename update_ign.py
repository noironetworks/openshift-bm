#The script does the following things:
#Update boostrap.ign with hostname.
#According to the number of the master count, create the JSON files, and add hostname/network-scripts.
#According to the number of the worker count, create the JSON files, and add hostname/network-scripts.

#Assumptions
#1 Interface Names: The RHCOS-4.6 OS Machines comes up with defined interface names viz. ens2, ens4, ens5
#2 Machine Names: The machine hostnames are based on <Infra-Id>-<bootstrap/master/worker>-<Number>
#3 Ignition Files: The new ignition files generated as per node viz. <Infra-Id>-bootstrap/master/worker-<index>-ignition.json 
#4 config.yaml: The script requires user-defined input file - config.yaml to be configured proper

#Script Run: python3 update_ign.py

#Expected Output: Igniton files <Infra-Id>-bootstrap/master/worker-<index>-ignition.json

#Expected Usage: The updated ignition files then can be used to bring up bootstrap and control plane via ansible playbooks

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


