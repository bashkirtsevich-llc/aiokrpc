class KRCPBasicException(Exception):
    pass


class KRPCErrorResponse(KRCPBasicException):
    pass


class KRPCResultError(KRCPBasicException):
    pass


class KRPCError(KRCPBasicException):
    def __init__(self, code, message):
        self._code = code
        super().__init__(message)

    @property
    def code(self):
        return self._code


class KRPCGenericError(KRPCError):
    def __init__(self):
        super().__init__(201, "Generic Error")


class KRPCServerError(KRPCError):
    def __init__(self):
        super().__init__(202, "Server Error")


class KRPCProtocolError(KRPCError):
    def __init__(self, message):
        super().__init__(203, message)


class KRPCMethodUnknownError(KRPCError):
    def __init__(self):
        super().__init__(204, "Method Unknown")
