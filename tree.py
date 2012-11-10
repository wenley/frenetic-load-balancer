import random
from help_lb import normalize

def uncommonAncestor(one, two):
    one2root = []
    two2root = []

    if one is two:
        return (one, two)

    n = one
    one2root.append(n)
    while n.parent is not None:
        n = n.parent
        one2root.append(n)
    n = two
    two2root.append(n)
    while n.parent is not None:
        n = n.parent
        two2root.append(n)

    n1 = one2root.pop()
    n2 = two2root.pop()
    while n1 is n2 and len(one2root) > 0 and len(two2root) > 0:
        n1 = one2root.pop()
        n2 = two2root.pop()
    return (n1, n2)

class LoadNode():
    '''
    Class of nodes. Value (cached) is the sum of its children's values.
    '''
    def __init__(self, value=0, parent=None):
        self.value = value
        self.origValue = value
        self.name = ''

        self.parent = parent
        self.left = None
        self.right = None
        self.sibling = None

        self.used = False

    # Specifically for greedy algorithms used with heapq
    # which is a minPQ.
    def __cmp__(self, other):
        if other.value != self.value:
            return other.value - self.value
        else: # Break ties by value of 1st uncommon ancestor
            (one, two) = uncommonAncestor(self, other)
            return two.value - one.value
    def __str__(self):
        return str((self.name, self.value))
    def __repr__(self):
        return self.__str__()

    def isLeaf(self):
        return self.left is None and self.right is None

    def update(self):
        if self.left is None and self.right is None:
            return
        self.value = 0
        if self.left is not None:
            self.left.update()
            self.value += self.left.value
        if self.right is not None:
            self.right.update()
            self.value += self.right.value

#    def makeTree(self, levels):
#        assert levels >= 0
#        if levels == 0:
#            return self
#        self.left = LoadNode(parent=self)
#        self.left.makeTree(levels - 1)
#        self.right = LoadNode(parent=self)
#        self.right.makeTree(levels - 1)

    def makeNames(self):
        if self.parent is None:
            self.name = ''
        if self.left is not None:
            self.left.name = self.name + '0'
            self.left.makeNames()
        if self.right is not None:
            self.right.name = self.name + '1'
            self.right.makeNames()

    def markUsed(self):
        self.used = True
        self.value = 0
        if self.left is not None:
            self.left.markUsed()
        if self.right is not None:
            self.right.markUsed()

class BinaryTree:
    '''
    Class for creating a binary tree
    '''

    def __init__(self, levels=1, weights=None):
        self.root = LoadNode()
        if levels > 0:
            leftTree = BinaryTree(levels - 1)
            self.root.left = leftTree.root
            self.root.left.parent = self.root

            rightTree = BinaryTree(levels - 1)
            self.root.right = rightTree.root
            self.root.right.parent = self.root

            self.root.left.sibling = self.root.right
            self.root.right.sibling = self.root.left

        self.root.makeNames()

        if weights is not None:
            assert len(weights) == (2 ** levels)
            leaves = self.leaves()
            for l, w in zip(leaves, weights):
                l.value = w
                l.origValue = w
            self.root.update()

    # The leaves of this tree
    def leaves(self, root=None, l=None):
        # Initialize
        if root is None:
            root = self.root
        if l is None:
            l = []

        if root.isLeaf():
            l.append(root)
            return l
        if root.left is not None:
            l = self.leaves(root=root.left, l=l)
        if root.right is not None:
            l = self.leaves(root=root.right, l=l)
        return l

    def level(self, depth, prev=None):
        if prev is None:
            prev = [self.root]
        if depth == 0:
            return prev
        else:
            prev2 = []
            for node in prev:
                if node.left is not None:
                    prev2.append(node.left)
                if node.right is not None:
                    prev2.append(node.right)
            prev = prev2
            return self.level(depth - 1, prev)

    def insert(self, binStr, root=None):
        if root is None:
            root = self.root

        root.value += 1
        if len(binStr) > 0 and binStr[0] == '0':
            self.insert(binStr[1:], root.left)
        elif len(binStr) > 0 and binStr[0] == '1':
            self.insert(binStr[1:], root.right)

class RandomTree(BinaryTree):
    '''
    Creates a balanced binary tree with random leaf values
    '''

    def __init__(self, levels=1, max=100, normal=None):
        numLeaves = 2 ** levels
        values = [random.randint(0, max) for i in range(numLeaves)]
        if normal is not None:
            values = normalize(values, normal)

        tree = BinaryTree(levels=levels, weights=values)
        self.root = tree.root


