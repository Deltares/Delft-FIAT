# distutils: language = c++
# cython: language_level=3
"""Shared FlatGeobuf constants and the low-level attribute codec.

Backed by the vendored FlatGeobuf C++ sources (declared in ``_bindings.pxd``).
The reader and writer modules ``cimport`` the codec helpers from here.
"""

from libc.stdint cimport uint16_t, uint32_t, uint64_t, uint8_t
from libc.string cimport memcpy
from libcpp.vector cimport vector


# --- Constants ------------------------------------------------------------
MAGIC = b"\x66\x67\x62\x03\x66\x67\x62\x01"

# GeometryType enum (FlatGeobuf).
GT_UNKNOWN = 0
GT_POINT = 1
GT_LINESTRING = 2
GT_POLYGON = 3
GT_MULTIPOINT = 4
GT_MULTILINESTRING = 5
GT_MULTIPOLYGON = 6

# ColumnType enum (FlatGeobuf).
CT_BYTE = 0
CT_UBYTE = 1
CT_BOOL = 2
CT_SHORT = 3
CT_USHORT = 4
CT_INT = 5
CT_UINT = 6
CT_LONG = 7
CT_ULONG = 8
CT_FLOAT = 9
CT_DOUBLE = 10
CT_STRING = 11
CT_JSON = 12
CT_DATETIME = 13
CT_BINARY = 14


# --- Property (attribute) codec -------------------------------------------
cdef bytes _bytes_from_ptr(const uint8_t* p, size_t n):
    """Copy a C buffer into a Python bytes object."""
    return (<char*>p)[:n]


# Little-endian readers: pull a fixed-width value out of a (possibly unaligned)
# byte pointer. The bytes are assembled explicitly so the result is independent
# of the host's endianness, and floats go through a bit-preserving ``memcpy``.
cdef inline uint16_t _get_u16(const uint8_t* p) noexcept nogil:
    return <uint16_t>(p[0] | ((<uint16_t>p[1]) << 8))


cdef inline uint32_t _get_u32(const uint8_t* p) noexcept nogil:
    return ((<uint32_t>p[0]) | ((<uint32_t>p[1]) << 8) |
            ((<uint32_t>p[2]) << 16) | ((<uint32_t>p[3]) << 24))


cdef inline uint64_t _get_u64(const uint8_t* p) noexcept nogil:
    cdef uint64_t v = 0
    cdef int b
    for b in range(8):
        v |= (<uint64_t>p[b]) << (8 * b)
    return v


cdef inline float _get_f32(const uint8_t* p) noexcept nogil:
    cdef uint32_t u = _get_u32(p)
    cdef float f
    memcpy(&f, &u, 4)
    return f


cdef inline double _get_f64(const uint8_t* p) noexcept nogil:
    cdef uint64_t u = _get_u64(p)
    cdef double d
    memcpy(&d, &u, 8)
    return d


# Little-endian writers: append a fixed-width value to a growing byte vector,
# mirroring the readers above (explicit byte order, ``memcpy`` for floats).
cdef inline void _put_u16(vector[uint8_t]& buf, uint16_t v) noexcept nogil:
    buf.push_back(<uint8_t>v)
    buf.push_back(<uint8_t>(v >> 8))


cdef inline void _put_u32(vector[uint8_t]& buf, uint32_t v) noexcept nogil:
    cdef int s
    for s in range(0, 32, 8):
        buf.push_back(<uint8_t>(v >> s))


cdef inline void _put_u64(vector[uint8_t]& buf, uint64_t v) noexcept nogil:
    cdef int s
    for s in range(0, 64, 8):
        buf.push_back(<uint8_t>(v >> s))


cdef inline void _put_f32(vector[uint8_t]& buf, float v) noexcept nogil:
    cdef uint32_t u
    memcpy(&u, &v, 4)
    _put_u32(buf, u)


cdef inline void _put_f64(vector[uint8_t]& buf, double v) noexcept nogil:
    cdef uint64_t u
    memcpy(&u, &v, 8)
    _put_u64(buf, u)


cdef object _decode_properties(const uint8_t* p, size_t n, list col_types):
    """Decode a FlatGeobuf property blob into a list aligned with columns.

    The blob is a tight little-endian stream of ``(uint16 column index, value)``
    records, where the value width depends on the column's type. Fixed-width
    numbers are read straight off the byte pointer; strings/binary are
    length-prefixed (uint32).
    """
    cdef Py_ssize_t ncol = len(col_types)
    # Pre-fill with None so columns absent from the blob stay null.
    cdef list values = [None] * ncol
    cdef size_t off = 0
    cdef uint16_t col
    cdef int ctype
    cdef uint32_t slen
    # Walk record by record until the blob is exhausted.
    while off + 2 <= n:
        # Each record starts with the little-endian column index.
        col = _get_u16(p + off)
        off += 2
        # Defensive: stop on an out-of-range column index.
        if col >= ncol:
            break
        # Dispatch on the column's FlatGeobuf type and advance past its value.
        # Signed/float values are reinterpreted from their little-endian bits.
        ctype = <int>(<object>col_types[col])
        if ctype == CT_BYTE:
            values[col] = <signed char>p[off]
            off += 1
        elif ctype == CT_UBYTE:
            values[col] = p[off]
            off += 1
        elif ctype == CT_BOOL:
            values[col] = bool(p[off])
            off += 1
        elif ctype == CT_SHORT:
            values[col] = <short>_get_u16(p + off)
            off += 2
        elif ctype == CT_USHORT:
            values[col] = _get_u16(p + off)
            off += 2
        elif ctype == CT_INT:
            values[col] = <int>_get_u32(p + off)
            off += 4
        elif ctype == CT_UINT:
            values[col] = _get_u32(p + off)
            off += 4
        elif ctype == CT_LONG:
            values[col] = <long long>_get_u64(p + off)
            off += 8
        elif ctype == CT_ULONG:
            values[col] = _get_u64(p + off)
            off += 8
        elif ctype == CT_FLOAT:
            values[col] = _get_f32(p + off)
            off += 4
        elif ctype == CT_DOUBLE:
            values[col] = _get_f64(p + off)
            off += 8
        elif ctype == CT_STRING or ctype == CT_JSON or ctype == CT_DATETIME:
            # Length-prefixed UTF-8 text.
            slen = _get_u32(p + off)
            off += 4
            values[col] = (<char*>(p + off))[:slen].decode("utf-8")
            off += slen
        elif ctype == CT_BINARY:
            slen = _get_u32(p + off)
            off += 4
            values[col] = (<char*>(p + off))[:slen]
            off += slen
        else:
            break
    return values


cdef bytes _encode_properties(list values, list col_types):
    """Encode a list of column values into a FlatGeobuf property blob.

    The inverse of :func:`_decode_properties`: each non-null value is written as
    ``(uint16 column index, little-endian value)``. Null values are skipped
    entirely (their column index simply never appears in the blob).
    """
    cdef vector[uint8_t] buf
    cdef Py_ssize_t i, n = len(values)
    cdef int ctype
    cdef bytes enc
    cdef const uint8_t* ep
    cdef uint8_t bval = 0
    for i in range(n):
        v = values[i]
        # Skip nulls; the decoder defaults missing columns back to None.
        if v is None:
            continue
        # Write the column index, then the value in the column's native width.
        # Each value is cast through its matching C type so signed/unsigned and
        # overflow semantics line up with the FlatGeobuf column type.
        ctype = <int>(<object>col_types[i])
        _put_u16(buf, <uint16_t>i)
        if ctype == CT_BOOL:
            bval = 1 if v else 0
            buf.push_back(bval)
        elif ctype == CT_BYTE:
            buf.push_back(<uint8_t><signed char>(<int>v))
        elif ctype == CT_UBYTE:
            buf.push_back(<uint8_t>(<unsigned int>v))
        elif ctype == CT_SHORT:
            _put_u16(buf, <uint16_t>(<int>v))
        elif ctype == CT_USHORT:
            _put_u16(buf, <uint16_t>(<unsigned int>v))
        elif ctype == CT_INT:
            _put_u32(buf, <uint32_t>(<int>v))
        elif ctype == CT_UINT:
            _put_u32(buf, <uint32_t>(<unsigned int>v))
        elif ctype == CT_LONG:
            _put_u64(buf, <uint64_t>(<long long>v))
        elif ctype == CT_ULONG:
            _put_u64(buf, <uint64_t>(<unsigned long long>v))
        elif ctype == CT_FLOAT:
            _put_f32(buf, <float>v)
        elif ctype == CT_DOUBLE:
            _put_f64(buf, <double>v)
        elif ctype == CT_STRING or ctype == CT_JSON or ctype == CT_DATETIME:
            # Length-prefixed UTF-8 text.
            enc = str(v).encode("utf-8")
            _put_u32(buf, <uint32_t>len(enc))
            ep = <const uint8_t*><char*>enc
            buf.insert(buf.end(), ep, ep + len(enc))
        elif ctype == CT_BINARY:
            enc = bytes(v)
            _put_u32(buf, <uint32_t>len(enc))
            ep = <const uint8_t*><char*>enc
            buf.insert(buf.end(), ep, ep + len(enc))
    # Hand back the contiguous blob (empty bytes when nothing was written).
    if buf.size() == 0:
        return b""
    return _bytes_from_ptr(buf.data(), buf.size())
