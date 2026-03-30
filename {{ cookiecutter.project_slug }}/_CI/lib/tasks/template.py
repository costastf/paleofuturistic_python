import logging
import shutil
import zipfile
from itertools import chain
from pathlib import Path
from tempfile import TemporaryDirectory

import invoke
from invoke import task

from .configuration import (BACKBONE_STRUCTURE,
                            PIP_COMPILE_CLI,
                            PROJECT_ROOT_DIRECTORY,
                            PYPROJECT_FILE,
                            REMOTE_GIT_ZIP_DIR,
                            REMOTE_ZIP_NAME,
                            TEMPLATE_NAME,
                            VENDOR_FILE,
                            VENDOR_BIN_DIRECTORY,
                            TASKS_DIRECTORY,
                            VENDORING_CLI,
                            WORKFLOW_SCRIPT_FILE)
from .utils import (delete_file_or_directory,
                    emojize_message,
                    pushd,
                    download_with_progress_bar,
                    make_file_executable,
                    get_binary_path)

LOGGER = logging.getLogger(__name__)


@task
def anonymize_pip_tools_command(context):
    text = open(VENDOR_FILE).read()
    start_marker = '--output-file='
    end_marker = 'lib/vendor.txt'
    text_to_remove = text[text.find(start_marker) + len(start_marker):text.find(end_marker)]
    text = text.replace(text_to_remove, '')
    VENDOR_FILE.write_text(text)
    LOGGER.info(emojize_message('Anonymized vendor.txt file appropriately.', success=True))


@task(post=[anonymize_pip_tools_command])
def clean_up_after_requirements_creation(context):
    """Called automatically by the create-requirements task, no use as a standalone command."""
    temporary_dir_name = f'{TEMPLATE_NAME.replace("-", "_")}.egg-info'
    LOGGER.info(f'Removing temporary directory "{temporary_dir_name}" if exists.')
    # Platform independent way to delete files or directories
    success = delete_file_or_directory(temporary_dir_name)
    LOGGER.info(emojize_message('Done!', success=success))


@task(post=[clean_up_after_requirements_creation])
def create_requirements(context):
    """Creates the vendor.txt file by using pip-tools that would parse the vendor entry or pyproject.toml."""
    arguments = ['--extra=vendor', '--resolver=backtracking', '-o', str(VENDOR_FILE), str(PYPROJECT_FILE), '--verbose']
    command = f'{PIP_COMPILE_CLI} {" ".join(arguments)}'
    LOGGER.info('Please wait while pip-tools runs pip-compile on pyproject.toml to create the vendor file.')
    LOGGER.debug(f'Running command: {command}')
    result = context.run(command, hide=True)
    exit_message = f'Successfully created {VENDOR_FILE}' if result.ok else result.stderr
    LOGGER.info(emojize_message(exit_message, success=result.ok))


@task
def generalise_python_shebang_in_bin(context):
    for file in VENDOR_BIN_DIRECTORY.glob('*'):
        try:
            with open(file, encoding='utf-8') as ifile:
                file_contents = ifile.readlines()
            file_contents[0] = '#!/usr/bin/env python\n'
            with open(file, 'w', encoding='utf-8') as ofile:
                ofile.writelines(file_contents)
            LOGGER.debug(f'Successfully updated shebang for file "{file}"')
        except UnicodeDecodeError:
            LOGGER.warning(f'File "{file}" does not seem to be a text file, cannot update the shebang.')
    LOGGER.info(emojize_message('Successfully updated shebang in all files under bin directory.'))


@task(pre=[create_requirements], post=[generalise_python_shebang_in_bin])
def update_libraries(context):
    """Updates the vendored dependencies by running the vendoring tool using vendor.txt requirements file."""
    arguments = ['sync', '.', '-v']
    command = f'{VENDORING_CLI} {" ".join(arguments)}'
    LOGGER.debug(f'Running command: {command}')
    result = context.run(command)
    message = emojize_message(f'Vendored all libraries status: {"Success!" if result.ok else "Failed!"}',
                              success=result.ok)
    LOGGER.info(message)


@task
def overwrite_from_remote_git(context):
    """Overwrites all remote existing files.

    Downloads the remote main branch as zip and overwrites all appropriate files of the _CI/ structure.

    """
    with TemporaryDirectory() as temp_dir, pushd(temp_dir):
        backbone_zip_path = download_with_progress_bar(REMOTE_GIT_ZIP_DIR, local_path=temp_dir)
        LOGGER.debug(f'Zip file path is {backbone_zip_path}')
        with zipfile.ZipFile(backbone_zip_path) as backbone_zip:
            backbone_zip.extractall()
        LOGGER.debug('Extracted all contents of the downloaded zip.')
        with pushd(REMOTE_ZIP_NAME):
            delete_file_or_directory(BACKBONE_STRUCTURE)
            LOGGER.debug(f'Copying tree of {Path(REMOTE_ZIP_NAME).resolve()} '
                         f'over {PROJECT_ROOT_DIRECTORY}')
            shutil.copytree('.', PROJECT_ROOT_DIRECTORY, dirs_exist_ok=True)
    for filename in chain([WORKFLOW_SCRIPT_FILE], VENDOR_BIN_DIRECTORY.iterdir()):
        make_file_executable(filename.resolve())
    LOGGER.info(emojize_message('Successfully overwrote the _CI directory with remote contents where possible',
                                success=True))


@task
def lint_tasks(context):
    """Lints the vendored tasks running the vendored ruff linter."""
    command = f'{get_binary_path("ruff")} {str(TASKS_DIRECTORY)}'
    LOGGER.debug(f'Running command: {command}')
    try:
        result = context.run(command).ok
    except invoke.exceptions.UnexpectedExit:
        result = False
    delete_file_or_directory('.ruff_cache')
    exit_message = f'{"Successfully linted" if result else "Linting failed for"} {TASKS_DIRECTORY}'
    LOGGER.info(emojize_message(exit_message, success=result))
