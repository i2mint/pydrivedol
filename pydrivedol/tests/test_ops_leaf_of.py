"""``ops._leaf_of`` resolves wrapper layers or refuses (no Google credentials needed)."""

import pytest
from dol import KeyCodecs

from pydrivedol.base import GDReader
from pydrivedol.ops import _leaf_of


class _KeyMappingLeaf(GDReader):
    def _id_of_key(self, k):
        return k


def _leaf():
    return _KeyMappingLeaf.__new__(_KeyMappingLeaf)


class _Opaque:
    def __init__(self, store):
        self.store = store


class _Delegating(_Opaque):
    """Forwards unknown attributes to the inner store: its ``_id_of_key`` is the leaf's."""

    def __getattr__(self, name):
        return getattr(self.store, name)


def test_leaf_and_dol_wrappers_resolve():
    leaf = _leaf()
    assert _leaf_of(leaf, GDReader) is leaf
    assert _leaf_of(KeyCodecs.prefixed("a/")(leaf), GDReader) is leaf


@pytest.mark.parametrize("wrapper", [_Opaque, _Delegating])
def test_layers_without_their_own_id_of_key_are_refused(wrapper):
    with pytest.raises(TypeError, match="_id_of_key"):
        _leaf_of(wrapper(_leaf()), GDReader)
