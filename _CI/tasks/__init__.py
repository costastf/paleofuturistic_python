import logging
import coloredlogs
from invoke import Collection

from _CI import (INVOKE_LOGGING_LEVEL,
                 validate_log_level)
from _CI.tasks.test import combo, list_combos, matrix, test

LOGGER = logging.getLogger(__file__)
coloredlogs.install(level=validate_log_level(INVOKE_LOGGING_LEVEL))

test_collection = Collection('test')
test_collection.add_task(test, default=True)
test_collection.add_task(combo)
test_collection.add_task(matrix)
test_collection.add_task(list_combos)

namespace = Collection()
namespace.add_collection(test_collection)
