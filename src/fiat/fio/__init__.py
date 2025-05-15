"""The I/O module of FIAT."""

import atexit
import weakref

from osgeo import gdal

from .buffer import *
from .fopen import *
from .geom import *
from .grid import *

_IOS = weakref.WeakValueDictionary()
_IOS_COUNT = 1

gdal.AllRegister()


def _add_ios_ref(wref):
    global _IOS_COUNT
    _IOS_COUNT += 1
    pass


def _DESTRUCT():
    items = list(_IOS.items())
    for _, item in items:
        item.close()
        del item


atexit.register(_DESTRUCT)
