from consMDP import ConsMDP
from math import inf
from reachability_examples import ultimate

m, targets = ultimate()

result = m.get_Buchi(targets, 15)
expected = [6, inf, inf, 3, 0, 1, 10, inf, 4, inf, inf]

assert result == expected, ("get_Buchi() returns" +
    " wrong values:\n" +
    f"  expected: {expected}\n  returns:  {result}\n")

# WIth cap < 15, we get all infs
result = m.get_Buchi(targets, 14)
expected = [inf, inf, inf, inf, inf, inf, inf, inf, inf, inf, inf]

assert result == expected, ("get_Buchi() returns" +
    " wrong values:\n" +
    f"  expected: {expected}\n  returns:  {result}\n")