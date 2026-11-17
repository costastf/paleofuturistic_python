"""The parent repository's task namespaces, aggregated for the launcher."""

from typing import cast

from invoke import Collection, Task

from _CI.tasks.document import build as document_build
from _CI.tasks.document import deploy_github as document_deploy_github
from _CI.tasks.document import document
from _CI.tasks.document import view as document_view
from _CI.tasks.lint import commitizen as lint_commitizen
from _CI.tasks.lint import complexipy as lint_complexipy
from _CI.tasks.lint import format_ as lint_format
from _CI.tasks.lint import lint
from _CI.tasks.lint import pylint as lint_pylint
from _CI.tasks.lint import ruff as lint_ruff
from _CI.tasks.lint import ty as lint_ty
from _CI.tasks.maintain import bump_uv, sync_docs, sync_vendor
from _CI.tasks.test import combo, invariants, list_combos, matrix, test

test_collection = Collection('test')
test_collection.add_task(cast(Task, test), default=True)
test_collection.add_task(cast(Task, combo))
test_collection.add_task(cast(Task, matrix))
test_collection.add_task(cast(Task, list_combos))
test_collection.add_task(cast(Task, invariants))

document_collection = Collection('document')
document_collection.add_task(cast(Task, document), default=True)
document_collection.add_task(cast(Task, document_build), name='build')
document_collection.add_task(cast(Task, document_view), name='view')
document_collection.add_task(cast(Task, document_deploy_github), name='deploy-github')

maintain_collection = Collection('maintain')
maintain_collection.add_task(cast(Task, bump_uv), name='bump-uv')
maintain_collection.add_task(cast(Task, sync_vendor), name='sync-vendor')
maintain_collection.add_task(cast(Task, sync_docs), name='sync-docs')

lint_collection = Collection('lint')
lint_collection.add_task(cast(Task, lint), default=True, name='all')
lint_collection.add_task(cast(Task, lint_ruff), name='ruff')
lint_collection.add_task(cast(Task, lint_format), name='format')
lint_collection.add_task(cast(Task, lint_pylint), name='pylint')
lint_collection.add_task(cast(Task, lint_ty), name='ty')
lint_collection.add_task(cast(Task, lint_complexipy), name='complexipy')
lint_collection.add_task(cast(Task, lint_commitizen), name='commitizen')

namespace = Collection()
namespace.add_collection(test_collection)
namespace.add_collection(document_collection)
namespace.add_collection(maintain_collection)
namespace.add_collection(lint_collection)
