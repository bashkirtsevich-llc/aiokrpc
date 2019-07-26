from aiokrpc.server import KRPCServer
from distutils.version import LooseVersion

__version__ = "0.0.4"
__version_info__ = tuple(LooseVersion(__version__).version)
__all__ = [
    "KRPCServer"
]
