from logging import getLogger, NullHandler

logger = getLogger("fast_bitrix24")
logger.addHandler(NullHandler())

def log(func):
    async def wrapper(*args, **kwargs):
        logger.info(f"Starting {func.__name__}({args}, {kwargs})")
        return await func(*args, **kwargs)
    return wrapper
