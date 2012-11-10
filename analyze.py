
import sys
from tree import *
from optparser import OptionParser

def analyze(input, prefix, depth):
    f = open(input, 'r')
    tree = BinaryTree(levels=depth)
    for line in f:
        toks = line.strip().strip(':').split('.')

        # Convert to binary and pad to 8 bits
        bins = [bin(int(tok))[2:] for tok in toks]
        pad = [''.join(['0' for i in range(8-len(bin))]) + bin for bin in bins]
        print pad

        full = ''.join(pad)
        tree.insert(full[:depth])
    f.close()

    nodes = [tree.root]
    for i in range(depth):
        nodes2 = []
        for node in nodes:
            if node.left is not None:
                nodes2.append(node.left)
            if node.right is not None:
                nodes2.append(node.right)
        nodes = nodes2
        f = open(prefix + str(i+1), 'w')
        f.write('\n'.join([str(n.value) for n in sorted(nodes)]))
        f.close()

def main():
    parser = OptionParser()
    parser.add_option('-p', '--prefix', type='string', action='store', dest='prefix')
    parser.add_option('-f', '--file', type='string', action='store', dest='input')
    parser.add_option('-d', '--depth', type='int', action='store', dest='depth', default=8)
    (options, args) = parser.parse_args()

    analyze(options.input, options.prefix, options.depth)

if __name__ == '__main__':
    main()
