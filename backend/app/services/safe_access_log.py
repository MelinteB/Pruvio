"""Do not emit callback query strings in application access logs."""
import logging

class SafeAccessFilter(logging.Filter):
    def filter(self, record):
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            target=args[2]
            if "?" in target:
                record.args=(*args[:2],target.split("?",1)[0]+"?[redacted]",*args[3:])
        return True

def install_access_filter():
    logger=logging.getLogger("uvicorn.access")
    if not any(isinstance(f, SafeAccessFilter) for f in logger.filters):
        logger.addFilter(SafeAccessFilter())
