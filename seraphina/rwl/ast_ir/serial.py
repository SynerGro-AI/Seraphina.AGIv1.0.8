"""Binary serialization of RWAST nodes.

Wire format (big-endian, self-delimiting):
    [u8  node_type ]
    [u16 n_children]
    [u16 data_len  ]   length of JSON-encoded data dict
    [u8* data      ]   UTF-8 JSON bytes
    [... children  ]   n_children serialised nodes (recursive)

The whole serialised tree is wrapped in the RWL1 byte-IR envelope with
language id "rwast" by the public API, giving it SHA256 tamper-evidence.
"""
from __future__ import annotations

import json
import struct
from io import BytesIO

from .nodes import Node, NodeType

_HDR = struct.Struct(">BHH")  # type u8, n_children u16, data_len u16


def pack(node: Node) -> bytes:
    """Serialise an RWAST node tree to bytes."""
    data_bytes = json.dumps(node.data, separators=(",", ":"),
                            ensure_ascii=False).encode("utf-8")
    header = _HDR.pack(int(node.kind), len(node.children), len(data_bytes))
    parts = [header, data_bytes]
    for child in node.children:
        parts.append(pack(child))
    return b"".join(parts)


def unpack(data: bytes | BytesIO) -> Node:
    """Deserialise an RWAST node tree from bytes."""
    buf = BytesIO(data) if isinstance(data, (bytes, bytearray)) else data
    header_bytes = buf.read(_HDR.size)
    if len(header_bytes) < _HDR.size:
        raise ValueError("truncated RWAST stream")
    kind_id, n_children, data_len = _HDR.unpack(header_bytes)
    try:
        kind = NodeType(kind_id)
    except ValueError:
        kind = NodeType.UNKNOWN
    raw_data = buf.read(data_len)
    if len(raw_data) < data_len:
        raise ValueError("truncated RWAST data field")
    node_data = json.loads(raw_data.decode("utf-8")) if data_len else {}
    children = [unpack(buf) for _ in range(n_children)]
    return Node(kind=kind, data=node_data, children=children)


def encode_tree(root: Node) -> bytes:
    """Pack a tree into the RWL byte-IR carrier (language='rwast')."""
    from ..codec import encode as _enc
    return _enc(pack(root), language="rwast", compress=True)


def decode_tree(blob: bytes) -> Node:
    """Unpack a tree from a RWL byte-IR blob (language='rwast')."""
    from ..codec import decode as _dec
    container, raw = _dec(blob)
    if container.language != "rwast":
        raise ValueError(f"expected language='rwast', got {container.language!r}")
    return unpack(raw)
