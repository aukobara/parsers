# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function, absolute_import

def is_immutable(self):
    raise TypeError('%r objects are immutable' % self.__class__.__name__)

# Copy-paste from Flask utility
class ImmutableListMixin(object):

    _hash_cache = None

    def _hashed_items(self):
        """Method for override if not all list items must be used in hash"""
        return self

    def __hash__(self):
        if self._hash_cache is not None:
            return self._hash_cache
        rv = self._hash_cache = hash(tuple(self._hashed_items()))
        return rv

    def __reduce_ex__(self, protocol):
        return type(self), (list(self),)

    def __delitem__(self, key):
        is_immutable(self)

    def __delslice__(self, i, j):
        is_immutable(self)

    def __iadd__(self, other):
        is_immutable(self)
    __imul__ = __iadd__

    def __setitem__(self, key, value):
        is_immutable(self)

    def __setslice__(self, i, j, value):
        is_immutable(self)

    def append(self, item):
        is_immutable(self)
    remove = append

    def extend(self, iterable):
        is_immutable(self)

    def insert(self, pos, value):
        is_immutable(self)

    def pop(self, index=-1):
        is_immutable(self)

    def reverse(self):
        is_immutable(self)

    def sort(self, cmp=None, key=None, reverse=None):
        is_immutable(self)

# Clone from IPython utility with some changes:
# 1) signature fix of update() and pop()
# 2) add post change notification to the same callbacks with post=True argument
# 3) version support - number incremented on each change. Initial dict has version 0

# void function used as a callback placeholder.
def _void(*p, **k): return None

class EventfulDict(dict):
    """Eventful dictionary.

    This class inherits from the Python intrinsic dictionary class, dict.  It
    adds events to the get, set, and del actions and optionally allows you to
    intercept and cancel these actions.  The eventfulness isn't recursive.  In
    other words, if you add a dict as a child, the events of that dict won't be
    listened to.  If you find you need something recursive, listen to the `add`
    and `set` methods, and then cancel `dict` values from being set, and instead
    set EventfulDicts that wrap those dicts.  Then you can wire the events
    to the same handlers if necessary.

    See the on_events, on_add, on_set, and on_del methods for registering
    event handlers."""

    def __init__(self, *args, **kwargs):
        """Public constructor"""
        self._add_callback = _void
        self._del_callback = _void
        self._set_callback = _void
        self._after_change_callback = _void
        self.version = 0
        super(EventfulDict, self).__init__(*args, **kwargs)

    def on_events(self, add_callback=None, set_callback=None, del_callback=None):
        """Register callbacks for add, set, and del actions.

        See the doctstrings for on_(add/set/del) for details about each
        callback.

        add_callback: [callback = None]
        set_callback: [callback = None]
        del_callback: [callback = None]"""
        self.on_add(add_callback)
        self.on_set(set_callback)
        self.on_del(del_callback)

    def on_add(self, callback):
        """Register a callback for when an item is added to the dict.

        Allows the listener to detect when items are added to the dictionary and
        optionally cancel the addition.

        callback: callable or None
            If you want to ignore the addition event, pass None as the callback.
            The callback should have a signature of callback(key, value).  The
            callback should return a boolean True if the additon should be
            canceled, False or None otherwise."""
        self._add_callback = callback if callable(callback) else _void

    def on_del(self, callback):
        """Register a callback for when an item is deleted from the dict.

        Allows the listener to detect when items are deleted from the dictionary
        and optionally cancel the deletion.

        callback: callable or None
            If you want to ignore the deletion event, pass None as the callback.
            The callback should have a signature of callback(key).  The
            callback should return a boolean True if the deletion should be
            canceled, False or None otherwise."""
        self._del_callback = callback if callable(callback) else _void

    def on_set(self, callback):
        """Register a callback for when an item is changed in the dict.

        Allows the listener to detect when items are changed in the dictionary
        and optionally cancel the change.

        callback: callable or None
            If you want to ignore the change event, pass None as the callback.
            The callback should have a signature of callback(key, value).  The
            callback should return a boolean True if the change should be
            canceled, False or None otherwise."""
        self._set_callback = callback if callable(callback) else _void

    def after_change(self, callback):
        """Register a callback for when an item is changed in the dict.

        Allows the listener to have notifications when items have been changed in the dictionary.

        callback: callable or None
            If you want to ignore the change event, pass None as the callback.
            The callback should have a signature of callback()."""
        self._after_change_callback = callback if callable(callback) else _void

    def pop(self, key, d=None):
        """Returns the value of an item in the dictionary and then deletes the
        item from the dictionary."""
        if self._can_del(key):
            r = dict.pop(self, key, d)
            self._post_del(key)
            return r
        else:
            raise Exception('Cannot `pop`, deletion of key "{}" failed.'.format(key))

    def popitem(self):
        """Pop the next key/value pair from the dictionary."""
        key = next(iter(self))
        return key, self.pop(key)

    def update(self, other_dict=None, **f):
        """Copy the key/value pairs from another dictionary into this dictionary,
        overwriting any conflicting keys in this dictionary."""
        changed = False
        if other_dict:
            for (key, value) in other_dict.items() if hasattr(other_dict, 'items') else other_dict:
                self.__setitem__(key, value, bulk_change=True)
                changed = True
        if f:
            for (key, value) in f.items():
                self.__setitem__(key, value, bulk_change=True)
                changed = True
        changed and self._changed()

    def clear(self):
        """Clear the dictionary."""
        changed = False
        for key in list(self.keys()):
            self.__delitem__(key, bulk_change=True)
            changed = True
        changed and self._changed()

    def __setitem__(self, key, value, bulk_change=False):
        if key in self:
            if self._can_set(key, value):
                r = dict.__setitem__(self, key, value)
                self._post_set(key, value, bulk_change)
                return r
        elif self._can_add(key, value):
            r = dict.__setitem__(self, key, value)
            self._post_add(key, value, bulk_change)
            return r

    def __delitem__(self, key, bulk_change=False):
        if self._can_del(key):
            r = dict.__delitem__(self, key)
            self._post_del(key, bulk_change)
            return r

    def _can_add(self, key, value):
        """Check if the item can be added to the dict."""
        return not bool(self._add_callback(key, value))

    def _can_del(self, key):
        """Check if the item can be deleted from the dict."""
        return not bool(self._del_callback(key))

    def _can_set(self, key, value):
        """Check if the item can be changed in the dict."""
        return not bool(self._set_callback(key, value))

    def _changed(self):
        self.version += 1
        self._after_change_callback()

    def _post_add(self, key, value, bulk_change):
        """Notify the item has been added to the dict."""
        self._add_callback(key, value, post=True)
        bulk_change or self._changed()

    def _post_del(self, key, bulk_change):
        """Notify the item has been deleted from the dict."""
        self._del_callback(key, post=True)
        bulk_change or self._changed()

    def _post_set(self, key, value, bulk_change):
        """Notify the item has been changed in the dict."""
        self._set_callback(key, value, post=True)
        bulk_change or self._changed()


class EventfulList(list):
    """Eventful list.

    This class inherits from the Python intrinsic `list` class.  It adds events
    that allow you to listen for actions that modify the list.  You can
    optionally cancel the actions.

    See the on_del, on_set, on_insert, on_sort, and on_reverse methods for
    registering an event handler.

    Some of the method docstrings were taken from the Python documentation at
    https://docs.python.org/2/tutorial/datastructures.html"""

    def __init__(self, *pargs, **kwargs):
        """Public constructor"""
        self._insert_callback = _void
        self._set_callback = _void
        self._del_callback = _void
        self._sort_callback = _void
        self._reverse_callback = _void
        super(EventfulList, self).__init__(*pargs, **kwargs)

    def on_events(self, insert_callback=None, set_callback=None,
        del_callback=None, reverse_callback=None, sort_callback=None):
        """Register callbacks for add, set, and del actions.

        See the doctstrings for on_(insert/set/del/reverse/sort) for details
        about each callback.

        insert_callback: [callback = None]
        set_callback: [callback = None]
        del_callback: [callback = None]
        reverse_callback: [callback = None]
        sort_callback: [callback = None]"""
        self.on_insert(insert_callback)
        self.on_set(set_callback)
        self.on_del(del_callback)
        self.on_reverse(reverse_callback)
        self.on_sort(sort_callback)

    def on_insert(self, callback):
        """Register a callback for when an item is inserted into the list.

        Allows the listener to detect when items are inserted into the list and
        optionally cancel the insertion.

        callback: callable or None
            If you want to ignore the insertion event, pass None as the callback.
            The callback should have a signature of callback(index, value).  The
            callback should return a boolean True if the insertion should be
            canceled, False or None otherwise."""
        self._insert_callback = callback if callable(callback) else _void

    def on_del(self, callback):
        """Register a callback for item deletion.

        Allows the listener to detect when items are deleted from the list and
        optionally cancel the deletion.

        callback: callable or None
            If you want to ignore the deletion event, pass None as the callback.
            The callback should have a signature of callback(index).  The
            callback should return a boolean True if the deletion should be
            canceled, False or None otherwise."""
        self._del_callback = callback if callable(callback) else _void

    def on_set(self, callback):
        """Register a callback for items are set.

        Allows the listener to detect when items are set and optionally cancel
        the setting.  Note, `set` is also called when one or more items are
        added to the end of the list.

        callback: callable or None
            If you want to ignore the set event, pass None as the callback.
            The callback should have a signature of callback(index, value).  The
            callback should return a boolean True if the set should be
            canceled, False or None otherwise."""
        self._set_callback = callback if callable(callback) else _void

    def on_reverse(self, callback):
        """Register a callback for list reversal.

        callback: callable or None
            If you want to ignore the reverse event, pass None as the callback.
            The callback should have a signature of callback().  The
            callback should return a boolean True if the reverse should be
            canceled, False or None otherwise."""
        self._reverse_callback = callback if callable(callback) else _void

    def on_sort(self, callback):
        """Register a callback for sortting of the list.

        callback: callable or None
            If you want to ignore the sort event, pass None as the callback.
            The callback signature should match that of Python list's `.sort`
            method or `callback(*pargs, **kwargs)` as a catch all. The callback
            should return a boolean True if the reverse should be canceled,
            False or None otherwise."""
        self._sort_callback = callback if callable(callback) else _void

    def append(self, x):
        """Add an item to the end of the list."""
        self[len(self):] = [x]

    def extend(self, L):
        """Extend the list by appending all the items in the given list."""
        self[len(self):] = L

    def remove(self, x):
        """Remove the first item from the list whose value is x. It is an error
        if there is no such item."""
        del self[self.index(x)]

    def pop(self, i=None):
        """Remove the item at the given position in the list, and return it. If
        no index is specified, a.pop() removes and returns the last item in the
        list."""
        if i is None:
            i = len(self) - 1
        val = self[i]
        del self[i]
        return val

    def reverse(self):
        """Reverse the elements of the list, in place."""
        if self._can_reverse():
            list.reverse(self)

    def insert(self, index, value):
        """Insert an item at a given position. The first argument is the index
        of the element before which to insert, so a.insert(0, x) inserts at the
        front of the list, and a.insert(len(a), x) is equivalent to
        a.append(x)."""
        if self._can_insert(index, value):
            list.insert(self, index, value)

    def sort(self, *pargs, **kwargs):
        """Sort the items of the list in place (the arguments can be used for
        sort customization, see Python's sorted() for their explanation)."""
        if self._can_sort(*pargs, **kwargs):
            list.sort(self, *pargs, **kwargs)

    def __delitem__(self, index):
        if self._can_del(index):
            list.__delitem__(self, index)

    def __setitem__(self, index, value):
        if self._can_set(index, value):
            list.__setitem__(self, index, value)

    def __setslice__(self, start, end, value):
        if self._can_set(slice(start, end), value):
            list.__setslice__(self, start, end, value)

    def _can_insert(self, index, value):
        """Check if the item can be inserted."""
        return not bool(self._insert_callback(index, value))

    def _can_del(self, index):
        """Check if the item can be deleted."""
        return not bool(self._del_callback(index))

    def _can_set(self, index, value):
        """Check if the item can be set."""
        return not bool(self._set_callback(index, value))

    def _can_reverse(self):
        """Check if the list can be reversed."""
        return not bool(self._reverse_callback())

    def _can_sort(self, *pargs, **kwargs):
        """Check if the list can be sorted."""
        return not bool(self._sort_callback(*pargs, **kwargs))


def get_subpackages(parent_pack, seen=None, debug=False, top_package=None, implicit_dep=None):
    import types, importlib

    top_package = top_package or parent_pack
    if debug:
        print("get_subpackages: %s, top: %s" % (parent_pack.__name__, top_package))

    child_mods = [mod for mod in parent_pack.__dict__.values() if isinstance(mod, types.ModuleType)]
    r = []
    seen = seen or set()
    seen.add(parent_pack)
    for mod in child_mods:
        if debug: print("Found child %s of %s" % (mod.__name__, parent_pack.__name__))
        if mod in seen or not mod.__name__.startswith(top_package.__name__ + '.'):
            if debug: print("Child %s has been seen or not inside. Skip" % mod.__name__)
            continue
        r.extend(get_subpackages(mod, seen=seen, debug=debug, top_package=top_package, implicit_dep=implicit_dep))
        if mod in implicit_dep:
            for dep_pack_name in implicit_dep[mod]:
                dep_mod = importlib.import_module(dep_pack_name)
                if debug: print("Found implicit dep %s of %s" % (dep_mod.__name__, mod.__name__))
                if dep_mod in seen:
                    if debug: print("Implicit dep %s has been seen. Skip" % dep_mod.__name__)
                    continue
                r.extend(get_subpackages(dep_mod, seen=seen, debug=debug, top_package=dep_mod, implicit_dep=implicit_dep))
                r.append(dep_mod)
                if debug: print("Implicit dep %s of %s added" % (dep_mod.__name__, mod.__name__))
        r.append(mod)
        if debug: print("Child %s of %s added" % (mod.__name__, parent_pack.__name__))
    if debug and not child_mods: print("No children found for %s" % parent_pack.__name__)
    return r


def to_str(something, encoding='utf-8'):
    """@rtype: unicode"""
    # This is to unify conversions from any type to unicode compatible with python 2.7 and 3.3+
    if something is None:
        return None
    if type(something) == unicode:
        return something
    if hasattr(something, '__unicode__'):
        return something.__unicode__()
    if isinstance(something, unicode):
        return something[:]
    s = something.decode(encoding) if isinstance(something, str) else str(something)
    try:
        s = s.decode('unicode-escape')
    except UnicodeEncodeError:
        pass
    try:
        s = s.encode('latin-1').decode('utf-8')
    except UnicodeEncodeError:
        pass
    return s