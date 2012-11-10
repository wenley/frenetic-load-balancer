import sys
import random
from help_lb import normalize

trials = 100
size = 5
biggest = 100
try:
    trials = int(sys.argv[1])
    size = int(sys.argv[2])
    biggest = int(sys.argv[3])
except:
    pass

pop = range(biggest)
for i in range(trials):
    k = random.sample(pop, size)
    n = normalize(k)
    print sum(n)

