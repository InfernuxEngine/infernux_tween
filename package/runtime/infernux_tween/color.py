"""RGBA list values backed by fixed native channels, with edits outside playback."""
from operator import index as integer_index, itemgetter
from dataclasses import dataclass

from infernux.lib._Infernux import _TweenColorChannels, _TweenColorPairChannels


def _channel(index):
    def write(self, value):
        self[index] = value
    return property(itemgetter(index), write)


class _ColorValue(list):
    __slots__ = ('_native',)
    r, g, b, a = (_channel(i) for i in range(4))

    def __init__(self, values):
        if isinstance(values, _ColorValue):
            self._native = _TweenColorChannels(values._native)
            super().__init__(values)
        else:
            self._native = _TweenColorChannels(tuple(values))
            super().__init__(self._native.values)

    @classmethod
    def _from_native(cls, native):
        value = cls.__new__(cls)
        value._native = native
        list.__init__(value, native.values)
        return value

    def __setitem__(self, index, value):
        if isinstance(index, slice):
            updated = list(self)
            updated[index] = value
            self._native.assign(updated)
            super().__setitem__(slice(None), self._native.values)
        else:
            index = integer_index(index)
            stored = self._native.set(index, value)
            super().__setitem__(index, stored)

    def reverse(self):
        self[:] = self[::-1]

    def sort(self, *, key=None, reverse=False):
        self[:] = sorted(self, key=key, reverse=reverse)

    def __copy__(self):
        return type(self)(self)

    def __deepcopy__(self, memo):
        return self.__copy__()

    def _fixed_size(self, *args, **kwargs):
        raise TypeError('colors have four fixed channels')

    append = clear = extend = insert = pop = remove = __delitem__ = __iadd__ = __imul__ = _fixed_size


def _color_value(values):
    return values if isinstance(values, _ColorValue) else _ColorValue(values)


@dataclass(init=False)
class Color2:
    __slots__ = ('_native_pair', '_ca_view', '_cb_view')
    ca: list[float]
    cb: list[float]

    def __init__(self, ca=(0., 0., 0., 0.), cb=(0., 0., 0., 0.)):
        self._native_pair = _TweenColorPairChannels(ca, cb)
        self._ca_view = self._cb_view = None

    @classmethod
    def _from_native(cls, native):
        value = cls.__new__(cls)
        value._native_pair = native
        value._ca_view = value._cb_view = None
        return value

    def _get_field(self, name):
        key = '_' + name + '_view'
        value = getattr(self, key)
        if value is None:
            value = _ColorValue._from_native(getattr(self._native_pair, name))
            setattr(self, key, value)
        return value

    def _set_field(self, name, values):
        key = '_' + name + '_view'
        previous = getattr(self, key)
        if previous is not None:
            detached = _TweenColorChannels(previous._native)
        setattr(self._native_pair, name, values)
        if previous is not None:
            previous._native = detached
        setattr(self, key, None)

    ca = property(lambda self: self._get_field('ca'), lambda self, value: self._set_field('ca', value))
    cb = property(lambda self: self._get_field('cb'), lambda self, value: self._set_field('cb', value))

    def __copy__(self):
        return type(self)._from_native(_TweenColorPairChannels(self._native_pair))

    def __deepcopy__(self, memo):
        return self.__copy__()

    def __getstate__(self):
        values = self._native_pair.values
        return {'ca': values[:4], 'cb': values[4:]}

    def __setstate__(self, state):
        self.__init__(state['ca'], state['cb'])

    def __iter__(self):
        return iter(self._native_pair.values)

    def __eq__(self, other):
        return self._native_pair.equals(other._native_pair) if isinstance(other, Color2) else NotImplemented

    def __add__(self, other):
        return Color2._from_native(self._native_pair.add(other._native_pair))

    def __sub__(self, other):
        return Color2._from_native(self._native_pair.subtract(other._native_pair))

    def __mul__(self, factor):
        return Color2._from_native(self._native_pair.multiply(factor))
