from loguru import logger
from pathlib import Path
from datetime import datetime
import os


def setup_logging(root: str, level: str = 'INFO'):
    logdir = Path(root) / datetime.now().strftime("%Y/%m/%d")
    logdir.mkdir(parents=True, exist_ok=True)
    logfile = logdir / "app.log"
    logger.remove()
    logger.add(str(logfile), rotation="00:00", retention="14 days", level=level, enqueue=True, backtrace=True, diagnose=True)
    logger.add(lambda m: print(m, end=""), level=level)
    return logger
