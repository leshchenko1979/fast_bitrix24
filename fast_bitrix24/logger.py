from logging import DEBUG, NullHandler, getLogger
from .__version__ import __version__


logger = getLogger("fast_bitrix24")
logger.setLevel(DEBUG)
logger.addHandler(NullHandler())

logger.debug(f"fast_bitrix24 version: {__version__}")

def log(func):
    async def wrapper(*args, **kwargs):
        logger.info(f"Starting {func.__name__}({args}, {kwargs})")
        return await func(*args, **kwargs)

    return wrapper
