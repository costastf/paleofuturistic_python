"""Checks on the suite's own locating helpers, over a hand-written module."""

import pytest

from .support import (
    function_named,
    function_source,
    imported_names,
    module_imports,
    parameter_defaults,
    task_source,
)

MODULE = '''\
"""A module shaped like a generated task module."""

import os
from .shared import execute, note

if os.name == 'nt':
    from .windows import opener

try:
    import tomllib
except ImportError:
    import tomli as tomllib


def helper(path, *, write=False):
    """Do the thing."""
    return execute(path)


@task
@logged('subject.run')
def run(context: Context, /, args: str = '', *rest, write: bool = False, **extra) -> None:
    """Run the subject.

    The docstring mentions `execute` before the body does.
    """
    note(helper(args, write=write))


def later():
    from .late import loaded  # noqa: PLC0415

    return loaded
'''


def test_function_source_is_the_function_and_nothing_else():
    """The text of one definition, decorators included, bounded by the definition itself."""
    helper = function_source(MODULE, 'helper')
    assert helper.startswith('def helper(')
    assert helper.endswith('return execute(path)\n')
    assert 'def run(' not in helper, 'the slice ran into the next definition'
    run = function_source(MODULE, 'run')
    assert run.startswith("@task\n@logged('subject.run')\ndef run("), 'the decorators are not part of the task'
    assert 'def later' not in run


def test_an_absent_function_fails_by_name():
    """A renamed function is a named failure, never an assertion over a neighbour's body."""
    with pytest.raises(LookupError, match="'missing'"):
        function_named(MODULE, 'missing')
    with pytest.raises(LookupError, match=r"'subject\.gone'"):
        task_source(MODULE, 'subject.gone')


def test_task_source_finds_a_function_by_its_logged_name():
    """A task is located by what `@logged` calls it, whatever the function is named."""
    assert task_source(MODULE, 'subject.run') == function_source(MODULE, 'run')


def test_parameter_defaults_read_every_kind_of_parameter():
    """Names and default sources, for positional-only, keyword-only and variadic parameters alike."""
    assert parameter_defaults(function_named(MODULE, 'run')) == {
        'context': None,
        'args': "''",
        'rest': None,
        'write': 'False',
        'extra': None,
    }
    assert parameter_defaults(function_named(MODULE, 'helper')) == {'path': None, 'write': 'False'}


def test_module_imports_are_what_runs_on_import():
    """Top-level imports count wherever they sit, and a function's own imports do not."""
    imports = module_imports(MODULE)
    assert 'from .shared import execute, note' in imports
    assert 'from .windows import opener' in imports, 'an import behind a module-level `if` is skipped'
    assert 'import tomli as tomllib' in imports, 'an import inside a module-level `try` is skipped'
    assert '.late' not in imports, 'an import deferred into a function is counted as paid at startup'
    assert imported_names(MODULE, '.shared') == {'execute', 'note'}
    assert imported_names(MODULE, '.late') == set()
