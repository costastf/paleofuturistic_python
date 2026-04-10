"""CI task definitions for the project workflow."""

from invoke import Collection

from . import bootstrap
from . import build
from . import container
from . import develop
from . import document
from . import format_
from . import lint
from . import quality
from . import secure
from . import test

namespace = Collection()
namespace.add_collection(bootstrap.namespace)
namespace.add_collection(build.namespace)
namespace.add_collection(container.namespace)
namespace.add_collection(develop.namespace)
namespace.add_collection(document.namespace)
namespace.add_collection(format_.namespace)
namespace.add_collection(lint.namespace)
namespace.add_collection(quality.namespace)
namespace.add_collection(secure.namespace)
namespace.add_collection(test.namespace)

# Wire bootstrap as a pre-task on all other top-level default tasks
_bootstrap_task = bootstrap.bootstrap
for _module in (build, container, develop, document, format_, lint, quality, secure, test):
    for _task in _module.namespace.tasks.values():
        _task.pre.insert(0, _bootstrap_task)
