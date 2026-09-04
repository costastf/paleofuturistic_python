"""CI task definitions for the project workflow."""

from pathlib import Path

from invoke import Collection

from . import (
    bootstrap,
    build,
    container,
    develop,
    document,
    format_,
    lint,
    preflight,
    quality,
    release,
    secure,
    test,
)

LOCAL_MODULE = Path(__file__).parent / 'local.py'

namespace = Collection()
namespace.add_collection(bootstrap.namespace)
namespace.add_collection(build.namespace)
namespace.add_collection(container.namespace)
namespace.add_collection(develop.namespace)
namespace.add_collection(document.namespace)
namespace.add_collection(format_.namespace)
namespace.add_collection(lint.namespace)
namespace.add_collection(preflight.namespace)
namespace.add_collection(quality.namespace)
namespace.add_collection(release.namespace)
namespace.add_collection(secure.namespace)
namespace.add_collection(test.namespace)

modules = [build, container, develop, document, format_, lint, preflight, quality, release, secure, test]

# `local` holds the tasks this project owns. It is picked up automatically so that adding a
# task never means editing this file — every module imported above belongs to the template and
# is replaced on `copier update`, so an entry added here would conflict on every one.
#
# A missing file means it was deliberately deleted, so it is skipped. An error *inside* it is
# deliberately left to propagate: silently dropping someone's tasks is worse than a traceback.
if LOCAL_MODULE.is_file():
    from . import local

    namespace.add_collection(local.namespace)
    modules.append(local)

# Wire bootstrap as a pre-task on all other top-level default tasks
bootstrap_task = bootstrap.bootstrap
for module in modules:
    for task in module.namespace.tasks.values():
        task.pre.insert(0, bootstrap_task)
