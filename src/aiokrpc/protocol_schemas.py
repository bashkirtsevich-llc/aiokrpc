COMMON_SCHEMA = {
    "t": {"type": "binary", "required": True},
    "y": {"type": "binary", "required": True, "allowed": [ord("q"), ord("r"), ord("e")]}
}
QUERY_SCHEMA = {
    "q": {"type": "binary", "required": True},
    "a": {"type": "dict", "required": True}
}
RESPONSE_SCHEMA = {
    "r": {"type": "dict", "required": True}
}
ERROR_SCHEMA = {
    "e": {"type": "list", "required": True, "items": [{"type": "integer"}, {"type": "binary"}]}
}