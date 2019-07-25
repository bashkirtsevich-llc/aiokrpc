import asyncio
from inspect import getfullargspec

from aioudp import UDPServer
from bencode import bdecode
from bencode import bencode
from cerberus import Validator

from .exceptions import KRPCError
from .exceptions import KRPCErrorResponse
from .exceptions import KRPCGenericError
from .exceptions import KRPCMethodUnknownError
from .exceptions import KRPCProtocolError
from .exceptions import KRPCResultError
from .exceptions import KRPCServerError
from .protocol_schemas import COMMON_SCHEMA, QUERY_SCHEMA, RESPONSE_SCHEMA, ERROR_SCHEMA


class KRPCServer(UDPServer):
    # region Public
    def __init__(self, **kwargs):
        super(KRPCServer, self).__init__(**kwargs)
        self.validator = Validator()
        self.callbacks = {}
        self.requests = {}
        self.tr_seq = 0

    def register_callback(self, callback, name=None, arg_schema=None, result_schema=None):
        if arg_schema and not isinstance(arg_schema, dict):
            raise TypeError("arg_schema must be 'dict' type")

        if result_schema and not isinstance(result_schema, dict):
            raise TypeError("result_schema must be 'dict' type")

        self.callbacks[name or callback.__name__] = {
            "cb": callback,
            "arg_schema": arg_schema or {},
            "result_schema": result_schema or {}
        }

    def callback(self, name=None, arg_schema=None, result_schema=None):
        def decorator(f):
            self.register_callback(f, name=name, arg_schema=arg_schema, result_schema=result_schema)

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

    def apply_schema(self, obj, schema, on_error, allow_unknown=True):
        self.validator.allow_unknown = allow_unknown
        if self.validator.validate(obj, schema):
            return self.validator.document
        else:
            return on_error(self.validator.errors)

    # endregion

    # region Query implementation
    async def catch_response(self, key):
        queue = asyncio.Queue(loop=self.loop)

        self.requests[key] = queue
        try:
            for attempt in range(3):
                try:
                    rt, response = await asyncio.wait_for(queue.get(), 10, loop=self.loop)
                    if rt == "e":
                        raise KRPCErrorResponse(response)
                    else:
                        return response
                except asyncio.TimeoutError as e:
                    if attempt == 2:
                        raise e
        finally:
            self.requests.pop(key)

    def ensure_query(self, addr, method, **kwargs):
        t = self.fetch_tr()
        msg = self.encode({"t": t, "y": "q", "q": method, "a": kwargs})
        self.send(msg, addr)

        return asyncio.ensure_future(self.catch_response(self.make_query_key(addr, t)), loop=self.loop)

    # endregion

    # region Responses
    def response(self, t, r, addr):
        msg = self.encode({"t": t, "y": "r", "r": r})
        self.send(msg, addr)

    def response_error(self, t, code, message, addr):
        msg = self.encode({"t": t, "y": "e", "e": [code, message]})
        self.send(msg, addr)

    # endregion

    # region Handlers
    async def handle_query(self, addr, q, a):
        def raise_arg_error(e):
            raise KRPCProtocolError(f"Arguments error ({str(e)})")

        def raise_result_error(e):
            raise KRPCResultError(f"Result error ({str(e)})")

        cb_info = self.callbacks.get(q)
        if cb_info:
            func = cb_info["cb"]
            arg_schema = cb_info["arg_schema"]
            result_schema = cb_info["result_schema"]

            spec = getfullargspec(func)
            args = {
                key: value
                for key, value in a.items()
                if spec.varkw is None or key in spec.args or key in spec.kwonlyargs
            }

            result = func(addr, **self.apply_schema(args, arg_schema, raise_arg_error))

            if asyncio.iscoroutine(result):
                result = await result

            return self.apply_schema(result, result_schema, raise_result_error)
        else:
            raise KRPCMethodUnknownError()

    def handle_response(self, addr, t, r):
        queue = self.requests.get(self.make_query_key(addr, t), None)
        if queue:
            queue.put_nowait(("r", (addr, r)))
        else:
            raise KRPCGenericError()

    def handle_error(self, addr, t, e):
        queue = self.requests.get(self.make_query_key(addr, t), None)
        if queue:
            queue.put_nowait(("e", (addr, e)))
        else:
            raise KRPCGenericError()

    # endregion

    # region Main loop
    async def datagram_received(self, data, addr):
        def raise_protocol_violation(e):
            raise KRPCProtocolError(f"Protocol violation ({str(e)})")

        try:
            msg = self.apply_schema(
                self.decode(data), COMMON_SCHEMA, raise_protocol_violation)

            t = msg["t"]
            y = msg["y"]
            try:
                if y == "q":
                    query = self.apply_schema(msg, QUERY_SCHEMA, raise_protocol_violation)
                    r = await self.handle_query(addr, query["q"], query["a"])
                    self.response(t, r, addr)

                elif y == "r":
                    response = self.apply_schema(msg, RESPONSE_SCHEMA, raise_protocol_violation)
                    self.handle_response(addr, t, response["r"])

                elif y == "e":
                    error = self.apply_schema(msg, ERROR_SCHEMA, raise_protocol_violation)
                    self.handle_error(addr, t, error["e"])

            except KRPCError as e:
                self.response_error(t, e.code, str(e), addr)

        except KRPCError as e:
            self.response_error(b"\x00\x00", e.code, str(e), addr)
    # endregion
