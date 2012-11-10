#!/usr/bin/python

# ---------------------------------------------------------------------
# In specifications below, [d] denotes the identifying number of a
# host in decimal and [xx] the same in hex.
#    e.g. r1 is server 1 and has MAC address 00:01:02:03:01:01
#         c3 is client 3 and has MAC address 00:01:02:03:02:03
#
# Switch s0 = Load Balancer. DPID: 80.
#    Port 1  --> Server-side switch
#    Port 2  --> Client-side switch
#    MACs unspecified
# Switch s1 = Server-side switch. DPID: 81
#    Port 1  --> Load Balancer
#       MAC unspecified
#    Port 2+ --> Replica Servers.
#       MAC: 00:01:02:03:11:[xx]
# Switch s2 = Client-side switch. DPID: 82
#    Port 1  --> Load Balancer
#       MAC unspecified
#    Port 2+ --> Client hosts
#       MAC: 00:01:02:03:22:[xx]
# Host r[d] = Replica servers
#    IP: 10.1.0.[d + 1]
#    MAC: 00:01:02:03:01:[xx]
# Host c[d] = Client hosts
#    IP: 10.2.0.[d + 1]
#    MAC: 00:01:02:03:02:[xx]
#
# NOTE: IPs of client client hosts are subject to change during tests.
# ---------------------------------------------------------------------





"""
Sets up the test harness for load balancer applications.

-S, --num-servers = Number of replica servers desired
-C, --num-clients = Number of client hosts desired
-I, --dummy-ip    = IP of server array 'revealed' to clients
-n, --num-tests   = Number of tests to run
-d, --delay       = Number of seconds to wait before first test

"""

import sys
import os
flush = sys.stdout.flush
from optparse import OptionParser
from mininet.net import init, Mininet
from mininet.node import KernelSwitch, UserSwitch, OVSKernelSwitch, RemoteController
from mininet.topo import Topo, Node
from mininet.log import lg
from mininet.log import info, error, debug, output
from mininet.cli import CLI
from mininet.term import *
import time
import random

START_TIME = 0
STATIC_ARP = True
DEBUG = False
switchTypes = {'us' : UserSwitch, 'ovsk' : OVSKernelSwitch}

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# Creates the network topology from scratch
# Uses the Mininet API to control MAC and IP at creation
def createNetwork(net, numserv, numclient):

#    cli = open('LB.cli', 'w')

    print "Adding controller..."
    net.addController('c0')

    print "Adding clients..."
    c = [None] # To make indices and names align
    for i in range(1, numclient + 1):
        # Start IP addresses at *.*.*.2
        name = 'c' + str(i)
        c.append(net.addHost(name, ip='10.2.0.' + str(i+1)))

    print "Adding replica servers..."
    r = [None]
    for i in range(1, numserv + 1):
        # Start IP addresses at *.*.*.2
        name = 'r' + str(i)
        r.append(net.addHost(name, ip='10.1.0.' + str(i+1)))

    print "Adding switches..."
    s = []
    s.append(net.addSwitch('s0', mac='00:00:00:00:00:80')) # Will be the Load Balancer
    s.append(net.addSwitch('s1', mac='00:00:00:00:00:81', ip='10.1.0.1')) # Server side
    s.append(net.addSwitch('s2', mac='00:00:00:00:00:82', ip='10.2.0.1')) # Client side

    print "Joining switches and hosts..."
    s[0].linkTo(s[1], port1=1, port2=1)
    s[0].linkTo(s[2], port1=2, port2=1)

    for i in range(1, len(r)):
        rep = r[i]
        intf1, intf2 = rep.linkTo(s[1])
        rep.setMAC(intf1, '00:01:02:03:01:%02x' % (i,))
        s[1].setMAC(intf2, '00:01:02:03:11:%02x' % (i,))
#        cli.write('r%d arp -s 10.1.0.1 00:01:02:03:11:%02d\n' % (i,i))
#        cli.write('%s ifconfig %s-eth0 10.1.0.%d/24\n' % (name, name, i+1))
#        cli.write('%s route add default gw 10.1.0.1\n' % (name,))
    for i in range(1, len(c)):
        client = c[i]
        intf1, intf2 = client.linkTo(s[2])
        client.setMAC(intf1, '00:01:02:03:02:%02x' % (i,))
        s[2].setMAC(intf2, '00:01:02:03:22:%02x' % (i,))
#        cli.write('c%d arp -s 10.2.0.1 00:01:02:03:22:%02d\n' % (i,i))
#    cli.close()

    return net

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

# Sets up proper IPs, ARP entries, and Gateways
# Needs to execute *after* net has been started
def configure(net):
    # Replica servers
    reps = [x for x in net.hosts if x.name[0] == 'r']
    for rep in reps:
        i = int(rep.name[1:])
        intf = rep.name + '-eth0'
        rep.setIP(intf, '10.1.0.%d' % (i+1,), 24)
        rep.cmd('route add default gw 10.1.0.1')
        rep.setARP('10.1.0.1', '00:01:02:03:11:%02x' %(i,))

    # Clients
    clis = [x for x in net.hosts if x.name[0] == 'c']
    for cli in clis:
        i = int(cli.name[1:])
        intf = cli.name + '-eth0'
        cli.setIP(intf, '10.2.0.%d' % (i+1,), 16)
        cli.cmd('route add default gw 10.2.0.1')
        cli.setARP('10.2.0.1', '00:01:02:03:22:%02x' %(i,))

    return net

# Runs pings between pairs of servers to initialize server-side switch
def intraServerPing(net, cliName):
    # Replica Servers
    reps = [x for x in net.hosts if x.name[0] == 'r']

    cli = open(cliName, 'w')
    r1 = reps[0]
    for rep in reps[1:]:
        cli.write('%s ping -c1 %s\n' % (r1.name, rep.name))
    cli.close()


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

def runServers(net):
    reps = [x for x in net.hosts if x.name[0] == 'r']

    print 'Starting up servers...'
    for rep in reps:
        rep.sendCmd('./mongoose/mongoose -e error_log%d &' % (int(rep.name[1:])))

def runClients(net, dummyIP='10.1.0.100', numtests=10, delay=9):
    clients = [x for x in net.hosts if x.name[0] == 'c']

    cmdFmt = 'wget %s:8080/ServerData/dummyfile --directory-prefix=HTML-c%s' % (dummyIP,'%02d')

    print 'Starting series of wget clients...'
    for client in clients:
        i = int(client.name[1:])
        pid = os.fork()
        if pid == 0:
            time.sleep(delay + i)
            for j in range(numtests):
                print 'Client %d sending request %d out of %d' % (i, j+1, numtests)
                client.cmd(cmdFmt % (i,))
                time.sleep(len(clients)/2) # Rough estimate to allow for non-overlapping requests
            print 'Client %d has finished' % (i,)
            sys.exit(0)

# Runs a series of wget requests from the clients with randomized IP addresses
def runRandomClients(net, dummyIP='10.1.0.100', numtests=10, delay=9):
    clients = [x for x in net.hosts if x.name[0] == 'c']

    cmdFmt = 'wget %s:8080/ServerData/dummyfile --directory-prefix=HTML-c%s' % (dummyIP, '%02d')

    # Distribution from which the first 8 bits of IPs will be chosen
    dist = lambda: random.randint(0, 255)
    full = lambda: (10, 2, dist(), dist())

    print 'Starting series of wget clients...'
    for client in clients:
        i = int(client.name[1:])
        pid = os.fork()
        if pid == 0:
            time.sleep(delay + i)
            for j in range(numtests):
                newSource = full()
                while newSource[0] == 10:
                    newSource = full()
                IP = '%d.%d.%d.%d' % newSource
                print 'Client %d changing IP to %s' % (i, '.'.join([str(n) for n in newSource]))
                client.cmd('ifconfig %s-eth0 %s' % (client.name, IP))

                print 'Client %d sending request %d out of %d from %s' % (i, j+1, numtests, IP)
                client.cmd(cmdFmt % (i,))
                time.sleep(len(clients)/2)
            print 'Client %d has finished' % (i,)
            sys.exit(0)

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

def start(stype, ip, port, numserv, numclient, dummyIP, numtests, delay):

    app='FreneticApp'

    # Initialize network
    net = Mininet(switch=switchTypes[stype],
                        controller=lambda name: RemoteController(name, defaultIP=ip, port=int(port)),
                        xterms=False )
    print "Creating topology..."
    net = createNetwork(net, numserv, numclient)

    print "Starting network..."
    net.start()

    print "Configuring network..."
    net = configure(net)

    ## Prime all hosts ARP caches
    if STATIC_ARP:
        net.staticArp()

    netElems = {}
    for h in net.hosts:
        netElems[h.name] = h
        if DEBUG:
            print "=== " + h.name + " Connections ==="
            print h.connection
    for s in net.switches:
        netElems[s.name] = s
        if DEBUG:
            print "=== " + s.name + " Connections ==="
            print s.connection
    for c in net.controllers:
        netElems[c.name] = c

    output("  *** Network Initialized in %s seconds***\n\n" % str(time.time()-START_TIME))

    # Wait for switch to register with controller
    time.sleep(3)

    # Run Test Harness
    yes = ['Y', 'y', 'yes', 'Yes', '']
    no = ['N', 'n', 'no', 'No', 'NO']
    print 'Waiting for controller: (Enter to continue) ',
    l = sys.stdin.readline() # Wait for prompt to continue

#    time.sleep(3) # Wait for controller to register
#    print 'Running intra-server pings...'
#    intraServerPing(net)
    print 'Start mongoose servers? [Y (default) / n ] ',
    l = sys.stdin.readline().strip()
    if l in no:
        print 'Not running mongoose servers'
    elif l in yes:
        runServers(net)
    else:
        print 'Unknown answer: ', l
        sys.exit(0)

#    print 'Writing intra-server pings to initialize switch entries'
#    CLIfile = 'LB.cli'
#    intraServerPing(net, CLIfile)

    print 'Automatic clients? [Y (default) / n ] ',
    l = sys.stdin.readline().strip()
    if l in no:
        print 'Not running automatic client wgets'
#        CLI(net, script=CLIfile)
    elif l in yes:
#        CLI(net, script=CLIfile)
        print 'Randomize client IPs? [Y (default) / n ] ',
        l = sys.stdin.readline().strip()
        if l in no:
            runClients(net, dummyIP=dummyIP, numtests=numtests, delay=delay)
        elif l in yes:
            runRandomClients(net, dummyIP=dummyIP, numtests=numtests, delay=delay)
        else:
            print 'Unknown answer: ', l
            sys.exit(0)
    else:
        print 'Unknown answer: ', l
        sys.exit(0)

    # Enter CLI mode for any finishing touches you might want to test
    output("*** Press ctrl-d or type exit to quit ***\n")
    # Change verbosity so that the output of CLI commands will display
    lg.setLogLevel('info')
    CLI(net)
    lg.setLogLevel('output')
    # All done, cleanup
#    netElems['h1'].cmd('sudo killall wbox dhclient')
    net.stop()


    os.system('sudo killall wget')
    os.system('sudo killall python')
    os.system('sudo killall mongoose')
    os.system('sudo killall /home/mininet/noxcore/build/src/.libs/lt-nox_core')


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -



def check_ip(i):
    l = i.split(".")
    if len(l) < 4 or len(l) > 4:
        return False
    else:
        for o in l:
            if not(o.isdigit()):
                return False
            if int(o) < 0 or int(o) > 255:
                return False
        return True

def check_controller(c):
    l = c.split(":")
    if l == [c]:
        # Should be a single IP
        if check_ip(c):
            return (c,"6633")
        else:
        # Maybe it's a port
            if c.isdigit():
                if (int(c) > 0 and int(c) < 65536):
                    return("127.0.0.1",c)
                else:
                    parser.error("Bad IP:Port")
            else:
                parser.error("Bad IP:Port")
    elif len(l) > 2:
        parser.error("Bad IP:Port")
    else:
        [ip,port] = l
        if check_ip(ip):
            if port.isdigit():
                if (int(port) > 0 and int(port) < 65536):
                    return (ip,port)
                else:
                    parser.error("Bad Port")
            else:
                parser.error("Bad Port")
        else:
            parser.error("Bad IP")

if __name__ == '__main__':
    # Lower verbosity level to suppress certain output.
    # SIDE EFFECT: CLI interactive output is supressed as well.
    # SOLUTION: Change verbosity before launching CLI
    lg.setLogLevel( 'output')
    MAXHOSTS = 100

    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)

    parser.add_option('-D', '--debug', action='store_true', dest='debug', default=False,
                        help='Debug the script with additional output.')
    parser.add_option('-t', "--switch-type", action="store", type='string', dest="st", default='us',
                        help="Type of switch to use [us|ovsk]. us = UserSwitch, ovsk = OpenVSwitch Kernel")
    parser.add_option('-c', "--controller-address", action="store", type='string', dest="controller", default='127.0.0.1:6633',
                        help="If specified, connects to a remote NOX instance IP:Port")
    parser.add_option('-a', "--full-arp", action="store_false", dest="full_arp", default=True,
                        help="Do *NOT* set static ARP entries and allow hosts to do ARP requests")
    parser.add_option('-S', "--num-servers", action="store", type="int", dest="numservers", default=2,
                        help="Number of servers for Load Balancer.")
    parser.add_option('-C', "--num-clients", action="store", type="int", dest="numclients", default=4,
                        help="Number of clients for Load Balancer.")
    parser.add_option('-I', "--dummy-ip", action="store", type="str", dest="dummyIP", default='10.1.0.100',
                        help='IP of server array revealed to clients.')
    parser.add_option('-n', "--num-tests", action="store", type="int", dest="numtests", default=10,
                        help="Number of wget tests to run per client.")
    parser.add_option('-d', '--delay', action='store', type='int', dest='delay', default=9,
                        help='Number of seconds to wait before first wget request from client.')

    (options, args) = parser.parse_args()

    # Check option validity
    if options.numservers > MAXHOSTS:
        parser.error("Too many servers. ")
    if options.numclients > MAXHOSTS:
        parser.error("Too many clients. ")
    if not (options.st in switchTypes.keys()):
        parser.error("Invalid switch type.")
    (ip,port) = check_controller(options.controller)
    START_TIME = time.time()
    STATIC_ARP = options.full_arp
    DEBUG = options.debug
    start(options.st, ip, port, options.numservers, options.numclients, options.dummyIP, options.numtests, options.delay)



