
import sys

# Normalizes the entries of seq to sum to a power of 2
def normalize(seq, t=None):

    total = sum(seq)

    # Determine desired total
    if t is not None:
        a = t
    else: # Default to a power of 2
        a = 1
        while a < total:
            a *= 2

    # No need to change if already sums to power of 2
    if a == total:
        return seq

    # Inflates seq so it totals a
    f = [float(i) * a  / total for i in seq]
    r = [int(round(i)) for i in f]
    if sum(r) == a:
        return r

    diffs = [ x[0] - x[1] for x in zip(f, r) ]

    # Helper function since cmp requires an integer return value
    def comp(x, y):
        if y[1] - x[1] < 0:
            return -1
        elif y[1] - x[1] > 0:
            return 1
        else:
            return 0

    if a - sum(r) > 0: # Need to add
        enum = enumerate(diffs)
        toSort = [(e[1], e[0]) for e in enum]
        s = sorted(toSort)
        i = 0
        while sum(r) < a:
            index = s[i % len(s)][1]
            r[index] += 1
            i += 1
    else: # Need to subtract
        enum = enumerate(diffs)
        toSort = [(e[1], e[0]) for e in enum]
        s = sorted(toSort)
        i = 0
        while sum(r) > a:
            index = s[i % len(s)][1]
            r[index] -= 1
            i += 1
    return r

# Takes list of (weight, server, binary weight) tuples and creates
# the appropriate list of nodes to allocate
# (weight, server, bin. weight) --> (weight, server, pow)
# NOTE: weights are negative because python heaps are minheaps
import heapq
def weights_to_nodes(weights):
    heapq.heapify(weights)
    nodes = []
    while len(weights) > 0:
#    for i in range(10):
        q = list(heapq.heappop(weights))
        n = (2**len(q[2][1:]), q[1], len(q[2][1:]))
        nodes.append(n)
        q[0] += n[0] # Since weights are stored as negatives
        q[2] = bin(-q[0])[2:] # Don't want leading '0b'
        if q[0] != 0:
            heapq.heappush(weights, tuple(q))
    return nodes

# Takes list of (num_leaves, server, power) nodes (as created by
# weights_to_nodes) and returns a list of rules of the form
# (prefix, server)
# (num_leaves, server, power) --> (prefix, server)
def nodes_to_rules(total_weight, nodes):
    power = 0
    i = 1
    while i < total_weight:
        i *= 2
        power += 1
    print 'Computed power:', power

    cum_sum = 0
    rules = []

    # Pads a string with leading zeros for total length length
    def pad(bin_str, length):
        len_pad = length - len(bin_str)
        if len_pad == 0:
            return bin_str
        pad_str = ''.join(['0' for i in range(len_pad)])
        return pad_str + bin_str

    for n in nodes:
        bin_str = bin(cum_sum)[2:]
        bin_str = pad(bin_str, power)
        if n[2] != 0:
            bin_str = bin_str[:-n[2]]
        rules.append((bin_str, n[1]))
        cum_sum += n[0]
    return rules

def test_normalize():
    pop = range(1, 21)
    k = random.sample(pop, 4)
    print 'k:', k
    n = normalize(k)
    print 'n:', n
    print 'sum:', sum(n)
    return n

def test_weights_to_nodes():
    n = test_normalize()
    print 'weights:', n
    weights = [(-x[1], x[0], bin(x[1])[2:]) for x in enumerate(n, 2)]
    nodes = weights_to_nodes(weights)
    print 'nodes:', nodes
    return nodes

def test_nodes_to_rules():
    nodes = test_weights_to_nodes()
    total_weight = sum([x[0] for x in nodes])
    rules = nodes_to_rules(total_weight, nodes)
    print 'rules:', rules

import random
if __name__ == '__main__':
#    test_normalize()
#    test_weights_to_nodes()
    test_nodes_to_rules()

