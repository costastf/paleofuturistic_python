import coloredlogs
from invoke import Collection

from . import template
from .configuration import INVOKE_LOGGING_LEVEL
from .utils import validate_log_level

coloredlogs.install(level=validate_log_level(INVOKE_LOGGING_LEVEL))

namespace = Collection()
namespace.add_task(template.create_requirements)
namespace.add_task(template.lint_tasks)
namespace.add_task(template.overwrite_from_remote_git)
namespace.add_task(template.update_libraries)
