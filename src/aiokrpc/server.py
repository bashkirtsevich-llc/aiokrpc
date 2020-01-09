import asyncio
from inspect import getfullargspec

from bencode import bdecode
from bencode import bencode
from cerberus import Validator

from .exceptions import KRPCError
from .exceptions import KRPCErrorResponse
from .exceptions import KRPCGenericError
from .exceptions import KRPCMethodUnknownError
from .exceptions import KRPCProtocolError
from .exceptions import KRPCResultError
from .protocol_schemas import COMMON_SCHEMA, QUERY_SCHEMA, RESPONSE_SCHEMA, ERROR_SCHEMA


class KRPCServer:
    # region Public
    def __init__(self, server, loop):
        self.validator = Validator()
        self.callbacks = {}
        self.requests = {}
        self.tr_seq = 0

        self.loop = loop

        self.server = server
        self.server.subscribe(self._parse_datagram)

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
        return await self._ensure_query(addr, method, **kwargs)

    # endregion

    # region Utils
    def _fetch_tr(self):
        self.tr_seq = (self.tr_seq + 1) % 0x10000
        return self.tr_seq.to_bytes(2, "big")

    @staticmethod
    def _make_query_key(addr, t):
        return hash((addr, t))

    @staticmethod
    def _encode(obj):
        return bencode(obj)

    @staticmethod
    def _decode(data):
        return bdecode(data, decoder=lambda ft, val: str(val, "utf-8") if ft == "key" else val)

    @staticmethod
    def server_version():
        return "aio-krpc"

    def _apply_schema(self, obj, schema, on_error, allow_unknown=True):
        self.validator.allow_unknown = allow_unknown
        if self.validator.validate(obj, schema):
            return self.validator.document
        else:
            return on_error(self.validator.errors)

    # endregion

    # region Query implementation
    async def _catch_response(self, key):
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
                    if attempt == 2:  # Attempt expired
                        raise e
        finally:
            self.requests.pop(key)

    def _ensure_query(self, addr, method, **kwargs):
        t = self._fetch_tr()
        msg = self._encode({"t": t, "y": "q", "q": method, "a": kwargs, "v": self.server_version()})

        self.server.send(msg, addr)

        return asyncio.ensure_future(self._catch_response(self._make_query_key(addr, t)), loop=self.loop)

    # endregion

    # region Responses
    def _send_response(self, t, r, addr):
        msg = self._encode({"t": t, "y": "r", "r": r, "v": self.server_version()})
        self.server.send(msg, addr)

    def _send_error_response(self, t, code, message, addr):
        msg = self._encode({"t": t, "y": "e", "e": [code, message], "v": self.server_version()})
        self.server.send(msg, addr)

    # endregion

    # region Handlers
    async def _handle_query(self, addr, q, a):
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

            result = func(addr, **self._apply_schema(args, arg_schema, raise_arg_error, spec.varkw is not None))

            if asyncio.iscoroutine(result):
                result = await result

            return self._apply_schema(result, result_schema, raise_result_error)
        else:
            raise KRPCMethodUnknownError()

    def _handle_response(self, addr, t, r):
        queue = self.requests.get(self._make_query_key(addr, t), None)
        if queue:
            queue.put_nowait(("r", (addr, r)))
        else:
            raise KRPCGenericError()

    def _handle_error_response(self, addr, t, e):
        queue = self.requests.get(self._make_query_key(addr, t), None)
        if queue:
            queue.put_nowait(("e", (addr, e)))
        else:
            raise KRPCGenericError()

    # endregion

    async def _parse_datagram(self, data, addr):
        def raise_protocol_violation(e):
            raise KRPCProtocolError(f"Protocol violation ({str(e)})")

        try:
            msg = self._apply_schema(self._decode(data), COMMON_SCHEMA, raise_protocol_violation)

            t = msg["t"]
            y = msg["y"]

            try:
                if y == "q":
                    query = self._apply_schema(msg, QUERY_SCHEMA, raise_protocol_violation)
                    r = await self._handle_query(addr, query["q"], query["a"])
                    self._send_response(t, r, addr)

                elif y == "r":
                    response = self._apply_schema(msg, RESPONSE_SCHEMA, raise_protocol_violation)
                    self._handle_response(addr, t, response["r"])

                elif y == "e":
                    error = self._apply_schema(msg, ERROR_SCHEMA, raise_protocol_violation)
                    self._handle_error_response(addr, t, error["e"])

            except KRPCError as e:
                self._send_error_response(t, e.code, str(e), addr)
        except:  # Just ignore any actions if we can't parse the packet
            # TODO: Print any errors into the error log
            pass
