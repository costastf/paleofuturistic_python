import logging
import coloredlogs
from invoke import Collection

from _CI import (INVOKE_LOGGING_LEVEL,
                 validate_log_level)

LOGGER = logging.getLogger(__file__)
coloredlogs.install(level=validate_log_level(INVOKE_LOGGING_LEVEL))

namespace = Collection()
