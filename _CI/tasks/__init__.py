import logging
import coloredlogs
from invoke import Collection

from _CI import (INVOKE_LOGGING_LEVEL,
                 validate_log_level)
from _CI.tasks.document import build as document_build
from _CI.tasks.document import deploy_github as document_deploy_github
from _CI.tasks.document import document
from _CI.tasks.document import view as document_view
from _CI.tasks.lint import format_ as lint_format
from _CI.tasks.lint import lint
from _CI.tasks.lint import ruff as lint_ruff
from _CI.tasks.maintain import bump_uv, sync_vendor
from _CI.tasks.test import combo, invariants, list_combos, matrix, test

LOGGER = logging.getLogger(__file__)
coloredlogs.install(level=validate_log_level(INVOKE_LOGGING_LEVEL))

test_collection = Collection('test')
test_collection.add_task(test, default=True)
test_collection.add_task(combo)
test_collection.add_task(matrix)
test_collection.add_task(list_combos)
test_collection.add_task(invariants)

document_collection = Collection('document')
document_collection.add_task(document, default=True)
document_collection.add_task(document_build, name='build')
document_collection.add_task(document_view, name='view')
document_collection.add_task(document_deploy_github, name='deploy-github')

maintain_collection = Collection('maintain')
maintain_collection.add_task(bump_uv, name='bump-uv')
maintain_collection.add_task(sync_vendor, name='sync-vendor')

lint_collection = Collection('lint')
lint_collection.add_task(lint, default=True, name='all')
lint_collection.add_task(lint_ruff, name='ruff')
lint_collection.add_task(lint_format, name='format')

namespace = Collection()
namespace.add_collection(test_collection)
namespace.add_collection(document_collection)
namespace.add_collection(maintain_collection)
namespace.add_collection(lint_collection)
