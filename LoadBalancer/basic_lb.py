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

# INITIALLY FLOOD EVERYWHERE AND NEVER FWD
flood_policy = Pol(PredTop(),[Action([],[openflow.OFPP_FLOOD])])
fwd_policy = BottomPolicy()

# Cleans up fwd and flood policies by walking them
def clean((fwd_policy, flood_policy)):
    fwd_policy = fwd_policy.walk(NV_parsePolUnion())
    flood_policy = flood_policy.walk(NV_parsePolUnion())
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
def initialize_LB((fwd_policy, flood_policy), num_servers=2, num_clients=4, dummy_ip='10.0.1.100'):

    # Modify flows going from servers towards clients
    pred = Pred('switch', 128) & Pred('srcip','10.0.1.0/24') & Pred('dstip','10.0.2.0/24') # Allows for 255 servers
    mods = [Mod('srcip', dummy_ip)]
    action = Action(mods, [2])
    p = Pol(pred, [action])
    fwd_policy = fwd_policy | p
    flood_policy = flood_policy - pred

    # Known Client IPs
    # Start at IP 10.0.2.2
    client_IPs = ['10.0.2.' + str(i) for i in range(2, 2+num_clients)]

    # Modify flows from clients towards servers
    for ip in client_IPs:
        server_num = (ipstr_to_int(ip) % num_servers) + 2 # Hash on last two bits and start at 2
        server_IP = '10.0.1.' + str(server_num)

        # For Packets coming from this client IP...
        pred = Pred('switch',128) & Pred('srcip',ip) & Pred('dstip',dummy_ip)
        mods = [Mod('dstip',server_IP)] # Change the destination IP
        action = Action(mods, [1])
        p = Pol(pred,[action])

        print "adjustPolicy %s, %s, %s" % (128, ip, p)
        fwd_policy = fwd_policy | p
        flood_policy = flood_policy - pred

    return clean((fwd_policy,flood_policy))

# Logic of Client Gateway
def setClientGateway((fwd_policy, flood_policy)):
    # Match client -> servers
    pred = Pred('switch', 130) & Pred('dstip', '10.0.1.0/24')
    action = Action([], [1]) # Send to Load Balancer
    p = Pol(pred, [action])
    fwd_policy = fwd_policy | p
    flood_policy = flood_policy - pred
    return clean((fwd_policy, flood_policy))

# Logic of Server Gateway
def setServerGateway((fwd_policy, flood_policy)):
    # Match server -> client
    pred = Pred('switch', 129) & Pred('dstip', '10.0.2.0/24')
    action = Action([], [1]) # Send to Load Balancer
    p = Pol(pred, [action])
    fwd_policy = fwd_policy | p
    flood_policy = flood_policy - pred
    return clean((fwd_policy, flood_policy))


# LEARNING SWITCH LOGIC
# d : IP --> (mac, port)
d = {}
def adjustPolicy(((switch,mac,ip),packet),(fwd_policy,flood_policy)):
    global d
    if switch == 128: # Load Balancer shouldn't learn
        return (fwd_policy, flood_policy)

    print "!!!! Following packet at switch %d, from port %s" % (switch, packet.header.inport)
    print packet

#    pred = Pred('switch',switch) & Pred('dstmac',mac)
#    action = Action([],[packet.header.inport])
#    p = Pol(pred,[action])
#    print "---- begin adjustPolicy --------"
#    print "pre-fwd_policy:\n%s" % fwd_policy
#    print "pre-flood_policy:\n%s" % flood_policy
#    print "adjustPolicy %s, %s, %s" % (switch, mac, p)
#    print "!!!stricture:\t%s" % p.predicate
#    print "!!!Strictures\n%s" % flood_policy.strictures()

    # FWD TO THE NEW PACKET SRC INSTEAD OF FLOODING
#    if not p in fwd_policy.rules():
#        fwd_policy = fwd_policy | p
#
#    if not p.predicate in flood_policy.strictures():
#        flood_policy = flood_policy - pred


    # ip should be from the switch's subnet to log an entry
    ip_int = ipstr_to_int(ip)
    if (switch == 129 and Pred('srcip', '10.0.1.0/24').wild_match(ip)) or \
        (switch == 130 and Pred('srcip', '10.0.2.0/24').wild_match(ip)):
        d[ip] = (mac, packet.header.inport)
        pred = Pred('switch', switch) & Pred('dstip', ip)
        mods = [Mod('dstmac', mac)]
        action = Action(mods, [packet.header.inport])
        p = Pol(pred, [action])
        fwd_policy = fwd_policy | p
        flood_policy = flood_policy - pred


#    # Add IP learning
#    if ipstr_to_int(ip) == 0:
#        return (fwd_policy,flood_policy)
#
#    pred = Pred('switch',switch) & Pred('dstip', ip)
#    mods = [Mod('dstmac',d[ip][0])]
#    action = Action(mods,[packet.header.inport])
#    p = Pol(pred,[action])
#
#    if p not in fwd_policy.rules():
#        fwd_policy = fwd_policy | p
#    if p.predicate not in flood_policy.strictures():
#        flood_policy = flood_policy - pred

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
        rules_e = q >> Probe("query results: ") >> ef
    return rules_e


def main(*args):
    # Extract arguments into variables
    num_servers = 2
    num_clients = 4
    dummy_ip = '10.0.1.100'
    print args
    try:
        num_servers = int(args[0])
        num_clients = int(args[1])
        dummy_ip = args[2]
    except IndexError:
        pass

    global fwd_policy
    global flood_policy
    (fwd_policy, flood_policy) = initialize_LB((fwd_policy, flood_policy), num_servers, num_clients, dummy_ip)
#    (fwd_policy, flood_policy) = initialize_Dumb_LB((fwd_policy, flood_policy))
#    print "!!!!! Forward policy:", fwd_policy
#    print "!!!!! Flood policy:", flood_policy
    (fwd_policy, flood_policy) = setServerGateway((fwd_policy, flood_policy))
#    print "!!!!! Foward after server:", fwd_policy
#    print "!!!!! Flood fter server:", flood_policy
    (fwd_policy, flood_policy) = setClientGateway((fwd_policy, flood_policy))
    print "!!!!! Final Initial forward:", fwd_policy
    print "!!!!! Final Initial flood:", flood_policy
    #arps = (Select('packets') *
    #        Where(dltype_fp(ethernet.ARP_TYPE)))
    #(arps >> process() >> Probe("pkt:\n") >> NOXSendPacket())
    return rules() >> Probe("policy:\n" ) >> Register()





