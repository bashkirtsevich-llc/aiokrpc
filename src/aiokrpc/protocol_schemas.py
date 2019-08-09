def _str_decode(s):
    return str(s, "utf-8")


COMMON_SCHEMA = {
    "t": {"type": "binary", "required": True},
    "v": {"type": "binary", "required": False},
    "y": {"type": "string", "required": True, "allowed": ["q", "r", "e"], "coerce": _str_decode}
}
QUERY_SCHEMA = {
    "q": {"type": "string", "required": True, "coerce": _str_decode},
    "a": {"type": "dict", "required": True}
}
RESPONSE_SCHEMA = {
    "r": {"type": "dict", "required": True}
}
ERROR_SCHEMA = {
    "e": {"type": "list", "required": True, "items": [{"type": "integer"}, {"type": "string", "coerce": _str_decode}]}
}
