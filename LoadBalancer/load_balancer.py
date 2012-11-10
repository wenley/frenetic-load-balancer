################################################################################
# The Frenetic Project                                                         #
# frenetic@frenetic-lang.org                                                   #
################################################################################
# Licensed to the Frenetic Project by one or more contributors. See the        #
# NOTICES file distributed with this work for additional information            #
# regarding copyright and ownership. The Frenetic Project licenses this        #
# file to you under the following license.                                     #
#                                                                              #
# Redistribution and use in source and binary forms, with or without           #
# modification, are permitted provided the following conditions are met:       #
# - Redistributions of source code must retain the above copyright             #
#   notice, this list of conditions and the following disclaimer.              #
# - Redistributions in binary form must reproduce the above copyright          #
#   notice, this list of conditions and the following disclaimer in            #
#   the documentation or other materials provided with the distribution.       #
# - The names of the copyright holds and contributors may not be used to       #
#   endorse or promote products derived from this work without specific        #
#   prior written permission.                                                  #
#                                                                              #
# Unless required by applicable law or agreed to in writing, software          #
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT    #
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the     #
# LICENSE file distributed with this work for specific language governing      #
# permissions and limitations under the License.                               #
################################################################################
# /src/examples/load_balancer.py                                               #
# Frenetic Static Load Balancer                                                #
# $Id$ #
################################################################################

from collections import defaultdict
from nox.coreapps.examples.frenetic_lib import *
from nox.coreapps.examples.frenetic_net import *
from nox.coreapps.examples.frenetic_netcore import *
from nox.lib.packet.packet_utils import *
from nox.lib.packet.ethernet import ethernet
from nox.lib.packet.arp import arp
from arpd import extractARP, extractARPType, extractRequest, extractReply
from learning_switch import adjustPolicy as learningPolicy

# DUMMY IP OF REPLICA SERVER ARRAY
dummy_ip = '10.0.1.100'

# Cleans up fwd and flood policies by walking them
def clean((fwd_policy, flood_policy)):
    fwd_policy = fwd_policy.walk(NV_parsePolUnion())
    flood_policy = flood_policy.walk(NV_parsePolUnion())
    return (fwd_policy, flood_policy)

# Static Load Balancer Logic
def initialize_LB(args):
    # INITIALLY FLOOD EVERYWHERE AND NEVER FWD
    flood_policy = Pol(PredTop(),[Action([],[openflow.OFPP_FLOOD])])
    fwd_policy = BottomPolicy()

    try:
        num_hosts = int(args[0])
    except:
        print >> sys.stderr, '\n-------------------------------'
        print >> sys.stderr, 'ERROR'
        print >> sys.stderr, "Usage: sudo ./frenetic_run load_balancer num_hosts [num_servers]"
        print >> sys.stderr, "ERR: Load Balancer module requires as argument the number of total hosts in the network"
        print >> sys.stderr, "Optional argument: The number of servers to be used in the network"
        print >> sys.stderr, '-------------------------------\n'
    else:
        print >> sys.stderr, '\nRunning with %d servers, balancing load over %d servers' % (num_hosts // 2, num_servers)
        print >> sys.stderr, 'Dummy IP is %s' % (dummy_ip,)
        print >> sys.stderr, '\n-------------------------------'
        print >> sys.stderr, "WARNING: Load Balancer module only works with 1-switch-bump topologies in sandbox"
        print >> sys.stderr, "Behavior unknown and not guaranteed with other topologies"
        print >> sys.stderr, '-------------------------------\n'

        global num_servers
        try:
            num_servers = int(args[1])
        except:
            num_servers = num_hosts // 2

        # Compute known server IPs
        # Requires coordination with sandbox.py
        global server_ips
        server_ips = ['10.0.1.%d' % (i+2,) for i in range(num_hosts // 2) ]


        # Modify flows going from servers towards clients
        pred = Pred('switch', 101) & Pred('inport', 1)
        mods = [Mod('srcip', dummy_ip)]
        action = Action(mods, [2])
        p = Pol(pred, [action])
        fwd_policy = fwd_policy | p
        flood_policy = flood_policy - pred

    return clean((fwd_policy,flood_policy))

# Load Balancer Logic
server_ips = []
num_servers = 1
def balancePolicy(((switch,mac,ip),packet),(fwd_policy,flood_policy)):

    # Perform hash and figure out renaming
    new_dst_ip = server_ips[ ipstr_to_int(packet.header.srcip) % num_servers ]
    new_macNum = int(new_dst_ip.split('.')[-1]) - 1
    new_mac = '00:00:00:00:00:%02x' % (new_macNum,)

    # Install rule
    pred = Pred('switch',switch) & Pred('srcip',packet.header.srcip) & Pred('dstip',dummy_ip)
    mods = [Mod('dstip',server_ips[ ipstr_to_int(ip) % num_servers ]), Mod('dstmac', new_mac)]
    action = Action(mods, [1])
    p = Pol(pred, [action])
    fwd_policy = fwd_policy | p
    flood_policy = flood_policy - pred

    return (fwd_policy, flood_policy)

# d : IP --> (mac, port)
def adjustPolicy(((switch,mac,ip),packet),(fwd_policy,flood_policy)):

    print "!!!! Following packet at switch %d, from port %s" % (switch, packet.header.inport)
    print packet

    # LOAD BALANCER LOGIC
    if switch == 101 and packet.header.inport == 2:
        (fwd_policy, flood_policy) = balancePolicy(((switch,mac,ip),packet),(fwd_policy,flood_policy))

    # Learning switch in all other areas
    elif switch != 101:
        (fwd_policy, flood_policy) = learningPolicy(((switch,mac),packet),(fwd_policy,flood_policy))

    return clean((fwd_policy,flood_policy))

def loadBalancer(args):

    (fwd_policy, flood_policy) = initialize_LB(args)

    # query: returns first packet from every host (identified by
    # its mac adress) on every switch each time it sends traffic
    # on a different input port.
    # IGNORE LLDP PACKETS AND IPV6 PACKETS (THEY ARE CAUSING TROUBLE AND CAN'T BE PARSED BY NOX)
    qrE = (Select('packets') *
           Where(or_fp([dltype_fp(ethernet.LLDP_TYPE, pol=False),dltype_fp(0x86dd,pol=False)])) *
           GroupBy(['switch','srcmac','srcip']) *
           SplitWhen(['inport']) *
           Limit(1))

    # ACCUMULATOR
    ef = (Accum((fwd_policy,flood_policy),adjustPolicy) >>
          Lift(lambda dbl: (dbl[0] | dbl[1]) - Pred('dltype',ethernet.LLDP_TYPE)))

    # APPLY ACCUMULATOR TO QUERY
    policyE = qrE >> Probe("query results: ") >> ef

    return policyE

def main(*args):
    return loadBalancer(args) >> Probe("policy:\n" ) >> Register()



