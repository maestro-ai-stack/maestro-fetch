from importlib.metadata import version as _pkg_version

from maestro_fetch.interfaces.sdk import fetch, batch_fetch

__all__ = ["fetch", "batch_fetch"]
__version__ = _pkg_version("maestro-fetch")
