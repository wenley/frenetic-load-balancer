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
# /src/examples/learnings_switch.py                                            #
# Frenetic learning switch                                                     #
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
from help_lb import *

# INITIALLY FLOOD EVERYWHERE AND NEVER FWD
flood_policy = Pol(PredTop(),[Action([],[openflow.OFPP_FLOOD])])
fwd_policy = BottomPolicy()

# Cleans up fwd and flood policies by walking them
def clean((fwd_policy, flood_policy)):
    fwd_policy = fwd_policy.walk(PV_parsePolUnion())
    flood_policy = flood_policy.walk(PV_parsePolUnion())
    return (fwd_policy, flood_policy)

# Used to initialize a dumb middle switch that simply passes
# all messages out the other port
def initialize_Dumb_LB((fwd_policy, flood_policy)):
    pred = Pred('switch', 128) & Pred('inport', 1)
    action = Action([], [2])
    p = Pol(pred, [action])
    fwd_policy = fwd_policy | p
    flood_policy = flood_policy - pred

    pred = Pred('switch', 128) & Pred('inport', 2)
    action = Action([], [1])
    p = Pol(pred, [action])
    fwd_policy = fwd_policy | p
    flood_policy = flood_policy - pred

    return clean((fwd_policy, flood_policy))

# Load Balancer Logic
# Assumes loads has already been normalized to sum to a power of 2
def initialize_LB((fwd_policy, flood_policy), num_servers=2, num_clients=4, dummy_ip='10.1.0.100', loads=None):

    # Modify flows going from servers towards clients
    pred = Pred('switch', 128) & Pred('srcip','10.1.0.0/24') # Allows for 255 servers
    mods = [Mod('srcip', dummy_ip)]
    action = Action(mods, [2])
    p = Pol(pred, [action])
    fwd_policy = fwd_policy | p
    flood_policy = flood_policy - pred

    # Calculate rules
    if loads is None:
        loads = [1, 1]
    bin_loads = [(-x[1], x[0], bin(x[1])[2:]) for x in enumerate(loads, 2)] # (Weight, Server, Binary Weight)
    nodes = weights_to_nodes(bin_loads)
    rules = nodes_to_rules(sum(loads), nodes)

    # Implement rules
    for rule in rules:
        IP_tail = int(rule[0]) << (16 - len(rule[0]))
        IP = '10.2.%d.%d' % ((IP_tail >> 8) & 0xff, IP_tail & 0xff)
        mask_len = 16 + len(rule[0])
        IP_match = IP + '/' + str(mask_len)

        pred = Pred('switch', 128) & Pred('srcip', IP_match) & Pred('dstip', '10.1.0.0/24')
        mods = [Mod('dstip', '10.1.0.' + str(rule[1]))]
        action = Action(mods, [1])
        p = Pol(pred, [action])

        print 'adjustPolicy %s, %s, %s' % (128, IP_match, p)
        fwd_policy = fwd_policy | p
        flood_policy = flood_policy - pred

    return clean((fwd_policy,flood_policy))

# Logic of Client Gateway
def setClientGateway((fwd_policy, flood_policy)):
    # Match client -> servers
    pred = Pred('switch', 130) & Pred('dstip', '10.1.0.0/24')
    action = Action([], [1]) # Send to Load Balancer
    p = Pol(pred, [action])
    fwd_policy = fwd_policy | p
    flood_policy = flood_policy - pred
    return clean((fwd_policy, flood_policy))

# Logic of Server Gateway
def setServerGateway((fwd_policy, flood_policy), numservers):
    # Make initial pings unnecessary
    # server IPs start at 2
    for i in range(2, 2 + numservers):
        ip = '10.1.0.' + str(i)
        mac = '00:01:02:03:01:%02x' % (i - 1,)
        pred = Pred('switch', 129) & Pred('dstip', ip)
        mods = [Mod('dstmac', mac)]
        action = Action(mods, [i]) # Ports align with IPs
        p = Pol(pred, [action])
        fwd_policy = fwd_policy | p
        flood_policy = flood_policy - pred

    return clean((fwd_policy, flood_policy))


# LEARNING SWITCH LOGIC
# d : IP --> (mac, port)
d = {}
def adjustPolicy(((switch,mac,ip),packet),(fwd_policy,flood_policy)):
    global d

    if switch == 128: # Load Balancer shouldn't learn for now (all clients in 10.2.*)
        return (fwd_policy, flood_policy)

    print "!!!! Following packet at switch %d, from port %s" % (switch, packet.header.inport)
    print packet

    # Only client switch remaps MAC
    # Learn on from-client packets
    ip_int = ipstr_to_int(ip)
    if switch == 130 and Pred('dstip', '10.2.0.0/16').wild_match(ip):
        print 'Client switch is learning'
        d[ip] = (mac, packet.header.inport)
        pred = Pred('switch', switch) & Pred('dstip', ip)
        mods = [Mod('dstmac', mac)]
        action = Action(mods, [packet.header.inport])
        p = Pol(pred, [action])
        fwd_policy = fwd_policy | p
        flood_policy = flood_policy - pred

    # Server switch and LB learn to send back to clients
    # TODO: Deal with multiple-IP MAC addresses
    if switch == 129 or switch == 128:
        pred = Pred('switch', switch) & Pred('dstip', ip)
        action = Action([], [packet.header.inport]) # Should be port 1
        p = Pol(pred, [action])
        fwd_policy = fwd_policy | p
        flood_policy = flood_policy - pred

#    print "post-fwd_policy:\n%s" % fwd_policy
#    print "post-flood_policy:\n%s" % flood_policy
#    print "---- end adjustPolicy --------"
    return clean((fwd_policy,flood_policy))

# rules : unit -> E policy
rules_e = None
def rules():
    global rules_e
    if rules_e is None:
        # query: returns first packet from every host (identified by
        # its mac adress) on every switch each time it sends traffic
        # on a different input port.
        q = (Select('packets') *
             GroupBy(['switch','srcmac','srcip']) *
             SplitWhen(['inport']) *
             Limit(1))
        # accumulate policy
        ef = (Accum((fwd_policy,flood_policy),adjustPolicy) >>
              Lift(lambda dbl: dbl[0] | dbl[1]))
        rules_e = q >> Probe("\nquery results: ") >> ef
    return rules_e


def main(*args):
    # Extract arguments into variables
    num_servers = 2
    num_clients = 4
    dummy_ip = '10.1.0.100'
    loads_file = '/home/openflow/frenetic/LoadBalancer/loads.txt'
    print args
    try:
        num_servers = int(args[0])
        num_clients = int(args[1])
        dummy_ip = args[2]
        loads_file = args[3]
    except IndexError:
        pass

    # Get desired server loads
    # TODO: When change policy, need to make sure in same base
    f = open(loads_file, 'r')
    loads  = f.readline().strip().split()
    loads = [int(x) for x in loads]
    loads = normalize(loads)
    f.close()

    global fwd_policy
    global flood_policy
    (fwd_policy, flood_policy) = initialize_LB((fwd_policy, flood_policy), num_servers, num_clients, dummy_ip, loads)
#    (fwd_policy, flood_policy) = initialize_Dumb_LB((fwd_policy, flood_policy))
#    print "!!!!! Forward policy:", fwd_policy
#    print "!!!!! Flood policy:", flood_policy
    (fwd_policy, flood_policy) = setServerGateway((fwd_policy, flood_policy), num_servers)
#    print "!!!!! Foward after server:", fwd_policy
#    print "!!!!! Flood fter server:", flood_policy
    (fwd_policy, flood_policy) = setClientGateway((fwd_policy, flood_policy))
    print "!!!!! Final Initial forward:", fwd_policy
    print "!!!!! Final Initial flood:", flood_policy
    #arps = (Select('packets') *
    #        Where(dltype_fp(ethernet.ARP_TYPE)))
    #(arps >> process() >> Probe("pkt:\n") >> NOXSendPacket())
    return rules() >> Probe("policy:\n" ) >> Register()





