import asyncio
from inspect import getfullargspec

from aioudp import UDPServer
from bencode import bdecode
from bencode import bencode
from cerberus import Validator

from .exceptions import KRPCError, KRPCGenericError, KRPCServerError, KRPCProtocolError, KRPCMethodUnknownError
from .protocol_schemas import COMMON_SCHEMA, QUERY_SCHEMA, RESPONSE_SCHEMA


class KRPCServer(UDPServer):
    # region Public
    def __init__(self, **kwargs):
        super(KRPCServer, self).__init__(**kwargs)
        self.validator = Validator()
        self.callbacks = {}
        self.requests = {}
        self.tr_seq = 0

    def register_callback(self, callback, name=None, arg_schema=None):
        if arg_schema and not isinstance(arg_schema, dict):
            raise TypeError("arg_schema must be 'dict' type")

        self.callbacks[name or callback.__name__] = {
            "cb": callback,
            "arg_schema": arg_schema or {}
        }

    def callback(self, name=None, arg_schema=None):
        def decorator(f):
            self.register_callback(f, name=name, arg_schema=arg_schema)

        return decorator

    async def call_remote(self, addr, method, **kwargs):
        return await self.ensure_query(addr, method, **kwargs)

    # endregion

    # region Utils
    def fetch_tr(self):
        self.tr_seq = (self.tr_seq + 1) % 0x10000
        return self.tr_seq.to_bytes(2, "big")

    @staticmethod
    def make_query_key(addr, t):
        return hash((addr, t))

    @staticmethod
    def encode(obj):
        try:
            return bencode(obj)
        except Exception as e:
            raise KRPCServerError() from e

    @staticmethod
    def decode(data):
        try:
            return bdecode(data, decoder=lambda ft, val: str(val, "utf-8") if ft == "key" else val)
        except Exception as e:
            raise KRPCProtocolError("Malformed packet") from e

    def validate(self, obj, schema, allow_unknown=True):
        self.validator.allow_unknown = allow_unknown
        return self.validator.validate(obj, schema)

    # endregion

    # region Query implementation
    async def catch_response(self, key):
        queue = asyncio.Queue(loop=self.loop)

        self.requests[key] = queue
        try:
            for attempt in range(3):
                try:
                    return await asyncio.wait_for(queue.get(), 10, loop=self.loop)
                except asyncio.TimeoutError as e:
                    if attempt == 2:
                        raise e
        finally:
            self.requests.pop(key)

    def ensure_query(self, addr, method, **kwargs):
        t = self.fetch_tr()
        msg = self.encode({"t": t, "y": b"q", "q": method, "a": kwargs})
        self.send(msg, addr)

        return asyncio.ensure_future(self.catch_response(self.make_query_key(addr, t)), loop=self.loop)

    # endregion

    # region Responses
    def response(self, t, r, addr):
        msg = self.encode({"t": t, "y": b"r", "r": r})
        self.send(msg, addr)

    def response_error(self, t, code, message, addr):
        msg = self.encode({"t": t, "y": b"e", "e": [code, message]})
        self.send(msg, addr)

    # endregion

    # region Handlers
    def handle_query(self, addr, q, a):
        cb_info = self.callbacks.get(str(q, "utf-8"), None)
        if cb_info:
            func = cb_info["cb"]
            schema = cb_info["arg_schema"]

            spec = getfullargspec(func)
            args = {
                key: value
                for key, value in a.items()
                if spec.varkw is None or key in spec.args or key in spec.kwonlyargs
            }

            if not self.validate(args, schema):
                raise KRPCProtocolError("Arguments error")

            return func(addr, **a)
        else:
            raise KRPCMethodUnknownError()

    def handle_response(self, addr, t, r):
        queue = self.requests.get(self.make_query_key(addr, t), None)
        if queue:
            queue.put_nowait((addr, r))
        else:
            raise KRPCGenericError()

    def handle_error(self, addr, t, e):
        queue = self.requests.get(self.make_query_key(addr, t), None)
        if queue:
            queue.put_nowait((addr, e))
        else:
            raise KRPCGenericError()

    # endregion

    # region Main loop
    async def datagram_received(self, data, addr):
        try:
            msg = self.decode(data)

            if not self.validate(msg, COMMON_SCHEMA):
                raise KRPCProtocolError("Basic protocol violation")

            t = msg["t"]
            y = msg["y"]
            try:
                if y == b"q":
                    if not self.validate(msg, QUERY_SCHEMA):
                        raise KRPCProtocolError("Query protocol violation")

                    r = self.handle_query(addr, msg["q"], msg["a"])

                    if asyncio.iscoroutine(r):
                        r = await r

                    self.response(t, r, addr)

                elif y == b"r":
                    if not self.validate(msg, RESPONSE_SCHEMA):
                        raise KRPCProtocolError("Response protocol violation")

                    self.handle_response(addr, t, msg["r"])

                elif y == b"e":
                    if not self.validate(msg, RESPONSE_SCHEMA):
                        raise KRPCProtocolError("Error protocol violation")

                    self.handle_error(addr, t, msg["e"])

            except KRPCError as e:
                self.response_error(t, e.code, str(e), addr)

        except KRPCError as e:
            self.response_error(b"\x00\x00", e.code, str(e), addr)
    # endregion
