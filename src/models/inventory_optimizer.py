"""
inventory_optimizer.py
LP-based inventory placement optimizer.
Algorithm : scipy.optimize.linprog (HiGHS solver)
Variables : x[w,r,c] = units shipped from warehouse w
            to region r for category c
Count     : 5 warehouses x 4 regions x 6 categories = 120
Scenarios : A (Cost), B (Balanced), C (Carbon)
"""
import numpy as np
from scipy.optimize import linprog

WAREHOUSES  = ["WH-NORTH","WH-SOUTH","WH-EAST","WH-WEST","WH-CENTRAL"]
REGIONS     = ["East","North","South","West"]
CATEGORIES  = ["BEAUTY","ELECTRONICS","HOME","KITCHEN","PET","TOYS"]

WH_CAPACITY = {
    "WH-NORTH"  : 120_000,
    "WH-SOUTH"  : 115_000,
    "WH-EAST"   : 118_000,
    "WH-WEST"   : 110_000,
    "WH-CENTRAL": 180_000,
}

SCENARIOS = [
    {"name":"A","label":"Cost Minimiser",  "w_cost":1.0,"w_carbon":0.0},
    {"name":"B","label":"Balanced",        "w_cost":0.6,"w_carbon":0.4},
    {"name":"C","label":"Carbon Champion", "w_cost":0.2,"w_carbon":0.8},
]


def build_index(warehouses, regions, categories):
    """Return flat-index function for (w,r,c) triple."""
    nreg = len(regions)
    ncat = len(categories)
    def idx(w, r, c):
        return (warehouses.index(w) * nreg * ncat
                + regions.index(r)  * ncat
                + categories.index(c))
    return idx


def solve(cost_coeff, carbon_coeff, demand, safety_stock,
          capacity, w_cost=0.6, w_carbon=0.4, relax=False):
    """Solve LP for given objective weights.
    Returns scipy OptimizeResult.
    """
    n = len(cost_coeff)
    c_max = cost_coeff.max()   or 1.0
    k_max = carbon_coeff.max() or 1.0
    obj   = w_cost * cost_coeff / c_max + w_carbon * carbon_coeff / k_max
    result = linprog(
        c      = obj,
        A_ub   = demand["A_ub"],
        b_ub   = demand["b_ub"],
        bounds = [(0, None)] * n,
        method = "highs",
    )
    return result


if __name__ == "__main__":
    print("inventory_optimizer.py — invoke via notebook cell B3")