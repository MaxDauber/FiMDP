"""
Core module defining basic data structures and classes of the FiMDP package.

It defines the class for representation of Consumption Decision Processes,
the interface for strategies (including exceptions), and Counter-strategies
(and the needed building blocks). Further, it provides support for ConsMDPs
that represent a product with some input ConsMDP and some other component
(explicit energy, automaton, ...).

## Consumption Markov Decision Processes (CMDPs)

See our [CAV paper] for the theoretical backgrounds.

The classes needed for representation of (CMDPs) are:
 * `ConsMDP`: represent an CMDP object
 * `ActionData`: represent actions of CMDPs

The `ProductConsMDP` are ConsMDPs with states fromed by 2 components.

## Interface for strategies

A `strategy` should offer `strategy.next_action()` that picks an action based
on history, and the function `strategy.update_state(outcome)` which tells the
strategy that the last action was resolved to the state outcome — which
becomes the new current state. Each call to `next_action()` should be
followed by a call to `update_state` and vice versa. Both functions raise
`WrongCallOrderError` if the calls do not alternate.

To simplify code, `strategy.next_action(outcome)` is a shorthand for

>>> strategy.update_state(outcome)
>>> strategy.next_action()

The function `update_state(outcome)` raises a `ValueError` if `outcome` is
not a valid successor for the last action returned by `next_action()`. Based
on the `outcome`, the strategy can update its memory.

The strategy can be used in a new play using `strategy.reset()` which allows
new initialization of initial state and memory.

The class `Strategy` implements the basic interface for strategies, but it
neither updates any memory nor picks actions. Its subclasses should override
the function `._next_action()` and (when using memory) also `._update(outcome)`.


## Counter-strategies

The main ingredient of a counter strategy is a *counter selector*. A counter
selector is a mapping from states to *selection rules*. A selection rule
selects actions based on given energy level. See, again, out [CAV paper] for
details.

The classes `CounterStrategy`, `CounterSelector`, and `SelectionRule` implement
the respective objects as described in the paper.

`ProductSelector` and `ProductSelectorWrapper` are two selectors that can be
used to hide the product construction from the user and maps actions and
states of a ProductConsMDP into states and actions of the original ConsMDP.

[CAV paper]: https://link.springer.com/chapter/10.1007/978-3-030-53291-8_22
"""

import math
from IPython.display import display, SVG

from .distribution import is_distribution
from .dot import consMDP2dot, dot_to_svg


class ConsMDP:
    """
    Represent Markov Decision Process with consumption on actions.

    States are represented by integers and actions are represented by
    `ActionData` objects. To add an action, use `add_action`. To iterate over
    actions of a state `s` use `actions_for_state(s)`. If you wish to remove
    actions during the iteration, use `out_iteraser(s)` instead. There is
    also `remove_action` which requires an action id. See implementation
    details for further info.

    States can have names using the list `names`. Reload states are stored
    in the set `reload_states`.

    Important
    =========
    Functions that change the structure of the consMDP should always call
    `self.structure_change()`.

    Define your probabilities in distributions in some exact representation
    like `decimal.Decimal(probability_string)` and always avoid floating-point
    data types. Due to their imprecision some checks could fail or trigger
    false positives (e.g. `0.06+0.82+0.12 != 1`!).

    Implementation details
    ======================
    The action objects are stored in a sparse-matrix fashion using two
    vectors: `succ` and `actions`. The latter is just a list of `ActionData`
    objects stored in the order in which the actions were created. Using
    the `ActionData.next_succ` the actions form a linked-list of actions
    for each state (that is how `actions_for_state(s)` work internally).
    The vector `succ` serves to locate the first action in this linked-list
    for given state (`actions[succ[s]]` hold the first action of `s`).

    Do not modify the two vectors directly. Always use `ConsMDP.add_action`
    to add and `ConsMDP.remove_action` or `ConsMDP.out_iteraser(s)` to remove
    actions.
    
    Computation of Safe vector
    ==========================
    The :math:`safe^{cap}` vector can be computed in 2 different ways.
    
    The variant used by default in consMDP can be controlled by def_EL_class.
    Currently, the default is 
    ```
    self.def_EL_class = BasicES
    ```
    The other option is `LeastFixpointES`.
    
    The running times between the 2 variants can vary a lot, it hugely
    depends on the MDP and its structure. See notebook 
    [Safe-variants](Safe-variants.ipynb) for more details and comparison.
    
    Basically, LeastFixpointES is faster on models where the maximal
    consumption on an action is strictly smaller than the number of states,
    and the other way.
    """

    def __init__(self):
        """Constructor method - consMDP class
        """
        self.name = None

        self.succ = []
        self.actions = [0]

        self.names = []
        self.names_dict = dict()
        self.reloads = []

        self.num_states = 0

    def structure_change(self):
        pass

    def state_with_name(self, name):
        '''Return id of state with name `name` or `None` if not exists.'''
        return self.names_dict.get(name)

    def new_state(self, reload=False, name=None):
        """Add a new state into the CMDP.

        Returns: the id of the created state
        Raise `ValueError` if a state with the same name already exists.
        """

        self.structure_change()

        # check for existing name
        if name is not None:
            s = self.state_with_name(name)
            if s is not None:
                raise ValueError("State with name \"{}\" already exists (id={})".
                                 format(name, s))
        
        sid = self.num_states
        
        self.succ.append(0)
        self.reloads.append(reload)
        self.names.append(name)
        if name is not None:
            self.names_dict[name] = sid
        self.num_states+=1
        return sid
    
    def new_states(self, count, names=None):
        #TODO add reload list
        """Create multiple (`count`) states.

        The list names must have length `count` if supplied. These will be
        the names for the states.

        Return the list of states ids.
        Raise `ValueError` if a state with the same name already exists.
        """
        if names is not None:
            if count != len(names):
                raise ValueError("Length of names must be equal to count.")

        self.structure_change()
        start = self.num_states
        for i in range(count):
            name = None if names is None else names[i]
            self.new_state(name)
        return range(start, start+count)

    def set_reload(self, sid, reload=True):
        #TODO extend to lists of states
        """Set reload status of state `sid`.

        Set to True by default."""
        self.structure_change()
        self.reloads[sid] = reload

    def unset_reload(self, sid):
        """Set the state `sid` *not* to be a reload state.

        Equivalent to
        ``
        set(sid, False)
        ``
        """
        self.structure_change()
        self.reloads[sid] = False

    def is_reload(self, sid):
        """Return the reload status of state `sid`."""
        return self.reloads[sid]

    def add_action(self, src, distribution, label, consumption = 0):
        """Add action to consMDP.

        Returns: index of the new action in the `actions` list.
        Raises: 
          * `ValueError` if attempt to use non-existent state
          * `ValueError` if src-label->... exists already. 
        """
        # Check that src exists
        if src >= self.num_states:
            raise ValueError(f"State {src} given as src does not exists.")

        # Check that all destinations exist
        for k in distribution.keys():
            if k >= self.num_states:
                raise ValueError(f"State {k} does not exists.")

        # check for determinism on action labels
        # raise ValueError if nondeterminsm would occur
        for a in self.actions_for_state(src):
            if a.label == label:
                raise ValueError(
                    "State {} already has an action with label {}".format(src, label))

        aid = len(self.actions)
        adata = ActionData(src, consumption, distribution, label, 0)

        self.structure_change()

        # Update the lists accordingly:
        #  * `next_succ` of last action for src if any, or
        #  * `succ[src]`  if it's first action for src
        a = self.actions_for_state(src).get_last()
        if a is None:
            self.succ[src] = aid
        else:
            a.next_succ = aid

        self.actions.append(adata)
        return aid

    def remove_action(self, aid):
        """Remove action based on its id."""
        # TODO add checks
        if aid <= 0 or aid >= len(self.actions):
            raise ValueError(f"The supplied aid {aid} is not a valid action id.")
        if self.actions[aid].next_succ == aid:
            raise ValueError(f"Action aid ({aid}) was already deleted.")

        self.structure_change()

        src = self.actions[aid].src
        it = self.out_iteraser(src)
        next(it)
        while it.curr != aid:
            next(it)
        it.erase()

    def actions_for_state(self, s):
        """Return iterator of actions available for state `s`."""
        it = _ActionIter(self.actions, self.succ[s])
        return it

    def out_iteraser(self, s):
        """
        Return iterator of actions available for state `s` that allows
        action removal.
        """
        it = _ActionItEraser(self, s)
        return it

    def state_succs(self, s):
        """Return successors of `s` over all actions"""
        succs = set()
        for e in self.actions_for_state(s):
            succs = succs.union(e.distr.keys())
        return succs

    def get_dot(self, options=""):
        dwriter = consMDP2dot(self, solver=None, options=options)
        return dwriter.get_dot()

    def show(self, options=""):
        return display(SVG(dot_to_svg(self.get_dot(options))))
        
    def _repr_dot_(self):
        return self.get_dot()

    def _repr_svg_(self):
        return dot_to_svg(self._repr_dot_())
        
        
class ActionData:
    """
    Holds data of an action in ConsMDP.

    The defining attributes of an action are:
     * source state `src`
     * consumption `cons`,
     * the successors probability distribution `distr`,
     * the action `label`

    The attribute `next_succ` is used to keep a nested linked-list of actions
    with the same `src`.
    """
       
    def __init__(self, src, cons, distr, label, next_succ):
        if not is_distribution(distr):
            raise AttributeError("Supplied dict is not a distribution." +
                                 " The probabilities are: {}, sum: {}".format
                                 (list (distr.values()),
                                  sum(distr.values())) )
        self.src = src
        self.cons = cons
        self.distr = distr
        self.label = label
        self.next_succ = next_succ
        
    def get_succs(self):
        return set(self.distr.keys())

    def __repr__(self):
        return f"{self.src}——{self.label}[{self.cons}]——>{self.distr}"


class _ActionIter:
    """
    Iterate over linked list nested in a given List.

    Expect that the items stored in `outer_list` contain field `next_succ` which
    contain integers that are indices in `outer_list` where new successor can be
    found.
    
    Assumptions
    ===========
     * List `outer_list` is indexed from 1
     * `item.next_succ == 0` means last item of the linked list (`succ`)

    Parameters
    ==========
     * outer_list: list of items containing `next_succ` fields. Indexed from 1.
     * start_index: (int) index in `outer_list` of the first element of the
        nested list that we want to iterate.
    
    """
    def __init__(self, outer_list, start_index):
        """Constructor method - _ActionIter class
        """
        # TODO check for types
        self.outer_list = outer_list
        self.next = start_index

    def __iter__(self):
        return self

    def __next__(self):
        if self.next == 0:
            raise StopIteration()
        if self.next >= len(self.outer_list):
            raise IndexError("{} ".format(self.outer_list) + f"{self.next}")
        else:
            item = self.outer_list[self.next]
            self.next = item.next_succ
            return item
        
    def is_empty(self):
        return self.next == 0
    
    def get_last(self):
        a = None
        while not self.is_empty():
            a = self.__next__()
        return a  
    
    def __len__(self):
        c = 0
        while not self.is_empty():
            a = self.__next__()
            c += 1
        return c


class _ActionItEraser(_ActionIter):
    """
    Iterate over outgoing edges of `s` and allow erasing edges.

    Expects an consMDP `mdp` and state index `s`. The function erase
    erases the current action and moves to the next one for `s`.
    """

    def __init__(self, mdp, s):
        """Constructor method - _ActionItEraser class
        """
        super(_ActionItEraser, self).__init__(mdp.actions, mdp.succ[s])
        self.curr = None
        self.prev = None
        self.s    = s
        self.succ = mdp.succ
        self.mdp = mdp

    def __next__(self):
        self.prev = self.curr
        self.curr = self.next
        return super(_ActionItEraser, self).__next__()

    def erase(self):
        if self.curr is None:
            raise ValueError("Can't erase before moved to 1st edge. "
                             "Call self.__next__() first")

        self.mdp.structure_change()

        self.outer_list[self.curr].next_succ = self.curr
        if self.prev is None:
            self.succ[self.s] = self.next
        else:
            self.outer_list[self.prev].next_succ = self.next


class ProductConsMDP(ConsMDP):
    """
    CMDP with states that have two components.

    We call the two components `orig_mdp` and `other`, where `orig_mdp` is
    some ConsMDP object and other can be arbitrary domain, for example
    deterministic Büchi automaton, or upper bound of some integer interval.
    The `orig_mdp` and `other` store pointers to the objects of origin for
      the product mdp (if supplied).

    The function `orig_action` maps actions in this object into actions of
    the source ConsMDP object. Similarly,  `other_action` works for the other
    object (if makes sense).
    """

    def __init__(self, orig_mdp, other=None):
        super().__init__()
        self.orig_mdp = orig_mdp
        self.other = other
        self.orig_action_mapping = {}
        self.other_action_mapping = {}
        self.components_to_states_d = {}
        self.components = []

    def add_action(self, src, distribution, label, consumption,
                   orig_action, other_action = None):
        """
        Create a new action in the product using (src, distribution, label,
        consumption) and update mappings to `orig_action` and `other_action`.

        :param src: src in product
        :param distribution: distribution in product
        :param label: label of the action
        :param consumption: consumption in product
        :param orig_action: ActionData object from the original mdp
        :param other_action: Value to be returned by `other_action` for the new
        action.
        :return: action id in the product
        """
        # pa: product action
        pa_id = super().add_action(src, distribution, label, consumption)
        pa = self.actions[pa_id]

        self.orig_action_mapping[pa] = orig_action
        if other_action is not None:
            self.other_action_mapping[pa] = other_action

        return pa_id

    def get_state(self, orig_s, other_s):
        """
        Return state of product based on the two components `(orig_s, other_s)`
        if exists and `None` otherwise.

        :param orig_s: state_id on the original mdp
        :param other_s: state of the other component
        :return: id of state `(orig_s, other_s)` or None
        """
        pair = (orig_s, other_s)
        return self.components_to_states_d.get(pair, None)

    def get_or_create_state(self, orig_s, other_s):
        """
        Return state of product based on the two components `(orig_s, other_s)`
        and create one if it does not exist.

        :param orig_s: state_id on the original mdp
        :param other_s: state of the other component
        :return: id of state `(orig_s, other_s)`
        """
        p_s = self.get_state(orig_s, other_s)
        if p_s is None:
            return self.new_state(orig_s, other_s)

        return p_s

    def new_state(self, orig_s, other_s, reload=False, name=None):
        """
        Create a new product state (orig_s, other_s).

        :param orig_s: state_id in the original mdp
        :param other_s: state of the other component
        :param reload: is state reloading? (Bool)
        :param name: a custom name of the state, `orig_s,other_s` by default.
        :return: id of the new state
        """
        if name is None:
            name = f"{orig_s},{other_s}"
        new_id = super().new_state(reload=reload, name=name)

        pair = (orig_s, other_s)
        self.components_to_states_d[pair] = new_id
        assert len(self.components) == new_id
        self.components.append(pair)

        return new_id

    def orig_action(self, action):
        """
        Decompose the action from the product to the action in the original mdp.

        :param action: ActionData from product (as used in for loops)
        :return: ActionData from the original mdp
        """
        return self.orig_action_mapping.get(action, None)

    def other_action(self, action):
        """
        Decompose the action from the product onto the second component, if
        defined.

        :param action: ActionData from product (as used in for loops)
        :return: value supplied on creation of `action` (if any), or None
        """
        return self.other_action_mapping.get(action, None)


### Strategies ###
class Strategy:
    """
    Abstract class that implements the interface for strategies (see the
    docstring for the `strategy.py` module). It handles the checks for
    outcomes and alternation of calls to `.next_action` and `.update_state`.

    Calls to `.next_action()` and `.update_state(outcome)` should alternate
    unless `next_action(outcome)` are used exclusively.
    """

    def __init__(self, mdp, init_state=None, *args, **kwargs):
        self.mdp = mdp
        self.reset(init_state, *args, **kwargs)

    def next_action(self, outcome=None):
        """
        Pick the next action to play

        :param outcome: sid (state id) or `None` (default `None`)
            `outcome` must be a successor of the action picked by the last call
            to `.next_action()`. If defined, update the current state to
            `outcome`.
        :return: action to play
        """
        if outcome is not None:
            self.update_state(outcome)
        if self._current_action is not None:
            raise WrongCallOrderError("The outcome of the last action is not "
                                      "known. Supply it using the `outcome` "
                                      "parameter or using the function"
                                      "`strategy.update_state(outcome)`.")
        self._current_action = self._next_action()
        return self._current_action

    def reset(self, init_state=None, *args, **kwargs):
        """Reset the memory and initial state for a new play."""
        self._current_action = None
        self._current_state = init_state
        self._reset(*args, **kwargs)

    def update_state(self, outcome):
        """
        Tells the strategy that the last action picked by `next_action` was
        resolved to `outcome`.

        :param outcome: sid (state id)
            `outcome` must be a successor of the action picked by the last call
            to `.next_action()`.
        """
        # Only run checks if this is not the first call to update_state
        # The first call basically sets the initial state
        if self._current_state is not None:
            if self._current_action is None:
                raise WrongCallOrderError("`strategy.update_state()` must be called"
                                          " after `strategy.next_action()`.")
            if outcome not in self._current_action.distr:
                raise ValueError(f"The outcome {outcome} is not a valid successor "
                                 f"for the last action picked by this strategy. "
                                 f"The list of possible outcomes is "
                                 f"{list(self._current_action.distr.keys())}.")
        self._update(outcome)
        self._current_action = None
        self._current_state = outcome

    def _next_action(self):
        raise NotImplementedError()

    def _reset(self, *args, **kwargs):
        pass

    def _update(self, outcome):
        pass


class CounterStrategy(Strategy):
    """
    Counter strategy tracks energy consumption in memory and chooses next
    action based on the current state and the current energy level.

    This class implements the memory and its updates. The selection itself is
    delegated to `selector`. The attributes `capacity` and `init_energy` are
    needed to track the energy level correctly.

    The implementation is suited to use CounterSelector as `selector`, but can
    take anything that implements `select_action(state, energy)`.
    """

    def __init__(self, mdp, selector, capacity,
                 init_energy, init_state=None, *args, **kwargs):
        super(CounterStrategy, self).__init__(mdp,
                                              init_state,
                                              init_energy=init_energy,
                                              *args, **kwargs)
        self.capacity = capacity
        self.selector = selector

    def _next_action(self):
        return self.selector.select_action(self._current_state, self.energy)

    def _update(self, outcome):
        """
        Unless called to set the initial state, update energy by substracting
        the consumption of the `_current_action`. If `_current_state` is a reload
        state, recharge to full capacity before the substraction.
        """
        # Don't update energy on the first call
        if self._current_action is not None:
            if self.mdp.is_reload(self._current_state):
                self.energy = self.capacity

            self.energy -= self._current_action.cons

    def _reset(self, init_energy=None, *args, **kwargs):
        """Reset the memory to `init_energy`.

        Throws away the previous history.

        *args and **kwargs are ignored.
        """
        if init_energy is not None:
            self.energy = init_energy


class CounterSelector(list):
    """
    CounterSelector selects actions based on given state and energy level.

    Counter selector is a list of SelectionRules extended by:
     * pointer to the corresponding mdp, and
     * 2 functions for updating and accessing actions to be taken:
        - update(state, energy_level, action)
        - select_action(state, energy)
    """

    def __init__(self, mdp, values=None):
        """
        ConsMDP `mdp` is where the selector picks actions.
        `values` can be a list of dicts with the values for the selector.
        """
        self.mdp = mdp
        self._init_selector(values)

    def _init_selector(self, values):
        num_states = self.mdp.num_states
        if values is None:
            for s in range(num_states):
                self.append(SelectionRule())
        else:
            assert len(values) == num_states
            assert len(self) == 0
            for rule in values:
                self.append(SelectionRule(rule))

    def update(self, state, energy_level, action):
        """
        Update the action for given `state` and `energy_level` to `action`.

        `energy_level` is a lower bound of an interval for which `action`
        will be selected by `select_action`.

        Raises ValueError if `product_action` is not an action of
        `product_state`
        """
        if action not in self.mdp.actions_for_state(state):
            raise ValueError(f"The action {action} is not valid for the state "
                             f"{state}.")
        self[state][energy_level] = action

    def select_action(self, state, energy):
        """
        Return action selected for `state` and `energy`
        """
        return self[state].select_action(energy)

    def copy_values_from(self, other, state_subset=None):
        """
        Replace values for given `state_subset` by values from `other` counter
        selector.

        If `state_subset` is not given (or is None), replace values for all
        states.
        """
        if state_subset is None:
            state_subset = range(self.mdp.num_states)

        for s in state_subset:
            self[s] = other[s].copy()

    def __copy__(self):
        """Return a shallow copy of the CounterSelector"""
        res = type(self)(self.mdp)
        for i, rule in enumerate(self):
            res[i] = (rule)
        return res

    def __deepcopy__(self, memodict={}):
        """Return a deep copy of the CounterSelector"""
        res = type(self)(self.mdp)
        for i, rule in enumerate(self):
            res[i] = (deepcopy(rule))
        return res


class ProductSelector(dict):
    """
    Selector suited for ConsMDPs whose analysis requires a product ConsMDP.

    It combines the approach of CounterSelector with decomposition of the
    product states and actions into the original components and works for
    selection even after destruction of the product MDP. The intended use is
    as follows.

    For a MDP called `orig` and some `other` object, we build `product` MDP.
    The analysis of `product` calls `ProductSelector.update()` with states
    and actions belonging to the product MDP. For selection of the next
    action, `ProductSelector.select_action` should be called with
    `orig_state` and `other_state` that belong to `orig` and `other` and no
    translation from/to product states is needed. Indeed, the translation
    happens directly on update.

    In short, based on information what action should be picked in a product
    (supplied using `update), ProductSelector selects actions of the original
    mdp (at the time `select_action` is called).

    It is implemented as 2-dimensional dict (other × orig) to SelectionRules.
    The reason for dicts instead of lists is that the product can be sparse.
    """

    def __init__(self, product_mdp: ProductConsMDP):
        self.product_mdp = product_mdp
        self.orig = product_mdp.orig_mdp
        self.other = product_mdp.other
        super(ProductSelector, self).__init__()

    def update(self, product_state, energy_level, product_action):
        """
        For given state of product with components `(orig, other)` update the
        selection rule for `selector[other][orig]` with `rule[energy]=action`
        where `action` belongs to `orig` and corresponds to `product_action`.

        energy_level` is a lower bound of an interval for which `action`
        will be selected by `select_action`.

        Raises ValueError if `product_action` is not an action of
        `product_state`
        """
        mdp = self.product_mdp
        if product_action not in mdp.actions_for_state(product_state):
            raise ValueError(f"The action {product_action} is not valid for "
                             f"the state {product_state}.")

        orig_state, other_state = mdp.components[product_state]
        orig_action = mdp.orig_action(product_action)
        orig_selector: dict = self.setdefault(orig_state, {})
        # rule = selector[other_state][orig_state]
        rule = orig_selector.setdefault(other_state, SelectionRule())
        rule[energy_level] = orig_action

    def select_action(self, orig_state, other_state, energy):
        """
        Return action selected for `orig_state×other_state` and `energy`.
        """
        try:
            rule: SelectionRule = self[orig_state][other_state]
        except KeyError:
            raise KeyError(f"There is no selection rule for the pair "
                           f"(orig_state, other_state) = "
                           f"({orig_state},{other_state})")

        return rule.select_action(energy)

    def copy_values_from(self, other, product_state_subset=None):
        """
        Replace values by values from `other` ProductSelector.

        If `product_state_subset` is not given (or is None), replace values for
        all states. Otherwise, replaces only those values that correspond to
        the given states from the product.
        """
        if product_state_subset is None:
            product_state_subset = range(self.product_mdp.num_states)

        for s in product_state_subset:
            orig_state, other_state = self.product_mdp.components[s]
            orig_selector: dict = self.setdefault(orig_state, {})
            orig_selector[other_state] = other[orig_state][other_state]

    def __copy__(self):
        """
        Return a shallow copy of the selector.

        The shallow copy creates new instances of both dimensions of the
        dictionaries, but reuses SelectionRules.
        """
        # Don't run ProductSelector's constructor in case product_mdp is
        # already deleted
        res = super(ProductSelector, self).__init__()
        res.product_mdp = self.product_mdp
        res.orig = self.orig
        res.other = self.other
        for other, selector in self.items():
            res_sel = res.setdefault(other, {})
            for orig, rule in selector:
                res_sel[orig] = rule

    def __deepcopy__(self, memodict={}):
        """
        Return a deep copy of the selector.

        The deep copy creates new instances of both dimensions of the
        dictionaries and also creates new SelectionRules.
        """
        res = super(ProductSelector, self).__init__()
        res.product_mdp = self.product_mdp
        res.orig = self.orig
        res.other = self.other
        for other, selector in self.items():
            res_sel = res.setdefault(other, {})
            for orig, rule in selector:
                res_sel[orig] = rule.copy()

    def __repr__(self):
        res = "===ProductSelector===\n"
        for mdp_s in sorted(self.keys()):
            for aut_s in self[mdp_s]:
                res += " "
                res += f"{mdp_s}×{aut_s}: "
                res += self[mdp_s][aut_s].__repr__()
                res += "\n"
        return res+"=====================\n"


class ProductSelectorWrapper(CounterSelector):
    """
    Selector suited for ConsMDPs whose analysis requires a product ConsMDP.

    The `ProductSelectorWrapper` is a wrapper around `CounterSelector` built
    for the product and the `ProductSelectorWrapper` translates the states of
    the product into their two components `(state, other_state)` and back.
    The same applies to actions.

    The main purpose of the selector is to provide interface that is
    accessible without the knowledge of the product. Therefore, it selects
    actions based on:
      * state of the original mdp (before product),
      * state of the other component, and
      * energy level.
    The actions returned by `select_action` are actions of the original mdp.
    """
    def __init__(self, mdp: ProductConsMDP, product_selector=None):
        super().__init__(mdp=mdp, values=product_selector)
        self.mdp = mdp

    def select_action(self, state, other_state, energy):
        p_s = self.mdp.get_state(state, other_state)
        p_a = super().select_action(p_s, energy)
        return self.mdp.orig_action(p_a)

    def __copy__(self):
        """Return a shallow copy of the ProductSelectorWrapper"""
        res = ProductSelectorWrapper(self.mdp)
        for rule in self:
            res.append(rule)
        return res

    def __deepcopy__(self, memodict={}):
        """Return a deep copy of the CounterSelector"""
        return ProductSelectorWrapper(self.mdp, product_selector=self)


class SelectionRule(dict):
    """
    Selection rule is a partial function: ℕ → Actions.

    Intuitively, a selection according to rule φ selects the action
    that corresponds to the largest value from dom(φ) that  is  not
    larger than the given energy level.

    For dom(φ) = n₁ < n₂ < ... < n_k and energy level e the selection
    returns φ(n_i) where i is largest integer such that n_i <= e.
    """

    def select_action(self, energy):
        """Select action for given energy level.

        :param energy: energy level
        :return: action selected by the rule for `energy`
        :raise: `NoFeasibleActionError` if no action can be selected for the
                given `energy`
        """
        candidate_interval, candidate_action = -1, None
        for lower_bound, action in self.items():
            if energy >= lower_bound > candidate_interval:
                candidate_interval, candidate_action = lower_bound, action

        if candidate_action is None:
            raise NoFeasibleActionError(f"No action is feasible for energy "
                                        f"level {energy}")
        return candidate_action

    def copy(self):
        return self.__copy__()

    def __copy__(self):
        return SelectionRule(self)

    def __deepcopy__(self, memodict={}):
        res = type(self)()
        for k, v in self.items():
            res[k] = v
        return res

    def __str__(self):
        """
        Print each rule as a line iof the form `interval: action.label`.
        """
        keys = sorted(self.keys())
        records = []
        for i, k in enumerate(keys):
            # Get the bounds of the intervals
            lower = k
            upper = keys[i+1] - 1 if i < len(keys) - 1 else None

            # Print l+ for the unbounded interval
            if upper is None:
                records.append(f"{lower}+: {self[k].label}")
            else:
                records.append(f"{lower} — {upper}: {self[k].label}")

        records_str = (',\n  ').join(records)
        return "{\n  " + records_str + "\n}"


class NoFeasibleActionError(Exception):
    pass


class WrongCallOrderError(Exception):
    pass


class PickFirstStrategy(Strategy):
    """Class for testing and presentation purposes.

    Always picks the first available action of the CMDP. Does not track energy
    and does not give any guarantees.
    """

    def _next_action(self):
        actions = self.mdp.actions
        a_id = self.mdp.actions_for_state(self._current_state).next
        return actions[a_id]
