"""Bound JSON complexity independently of the interpreter's recursion limit."""
import json


def loads_bounded(body, *, max_bytes=65536, max_depth=8):
    if len(body) > max_bytes:
        raise ValueError('JSON body too large')
    text = body.decode('utf-8') if isinstance(body, bytes) else body
    depth = 0
    quoted = False
    escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in '[{':
            depth += 1
            if depth > max_depth:
                raise ValueError('JSON nesting limit exceeded')
        elif char in ']}':
            depth -= 1
    return json.loads(text)
