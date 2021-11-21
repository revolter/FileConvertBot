from __future__ import annotations

import configparser
import datetime
import os
import typing

import fabric
import invocations.console
import invoke

import invoke_patch
import src.constants


class GlobalConfig:
    host: str
    user: str
    key_filename: str
    project_name: str
    project_path: str

    source_filenames = [
        'main.py',
        'database.py',
        'utils.py',
        'telegram_utils.py',
        'analytics.py',
        'constants.py',

        'custom_logger.py',

        'config.cfg'
    ]
    meta_filenames = [
        'pyproject.toml',
        'poetry.lock'
    ]
    source_directories = [
        'migrations'
    ]

    @classmethod
    def load(cls) -> None:
        try:
            fabfile_config = configparser.ConfigParser()

            fabfile_config.read('fabfile.cfg')

            cls.host = fabfile_config.get('Fabric', 'Host')
            cls.user = fabfile_config.get('Fabric', 'User')
            cls.key_filename = os.path.expanduser(fabfile_config.get('Fabric', 'KeyFilename'))
            cls.project_name = fabfile_config.get('Fabric', 'ProjectName')
            cls.project_path = fabfile_config.get('Fabric', 'ProjectPath')
        except configparser.Error as error:
            raise invoke.Exit(
                message=f'Config error: {error}',
                code=1
            )


invoke_patch.fix_annotations()
GlobalConfig.load()


@fabric.task
def configure(connection: fabric.Connection) -> None:
    connection.user = GlobalConfig.user
    connection.inline_ssh_env = True
    connection.connect_kwargs.key_filename = GlobalConfig.key_filename


@fabric.task(pre=[configure], hosts=[GlobalConfig.host], help={'command': 'The shell command to execute on the server', 'env': 'An optional dictionary with environment variables'})
def execute(connection: fabric.Connection, command: str, env: typing.Dict[str, str] = None) -> None:
    if not command:
        return

    connection.run(command, env=env)


@fabric.task(pre=[configure], hosts=[GlobalConfig.host])
def cleanup(connection: fabric.Connection) -> None:
    question = f'Are you sure you want to completely delete the project "{GlobalConfig.project_name}" from "{GlobalConfig.host}"?'

    if invocations.console.confirm(
        question=question,
        assume_yes=False
    ):
        execute(connection, f'rm -rf {GlobalConfig.project_name}')
        execute(connection, f'rm -rf {GlobalConfig.project_path}/{GlobalConfig.project_name}')


@fabric.task(pre=[configure, cleanup], hosts=[GlobalConfig.host])
def setup(connection: fabric.Connection) -> None:
    execute(connection, f'mkdir -p {GlobalConfig.project_path}/{GlobalConfig.project_name}')
    execute(connection, f'ln -s {GlobalConfig.project_path}/{GlobalConfig.project_name} {GlobalConfig.project_name}')

    execute(connection, 'curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/install-poetry.py | python -')


@fabric.task(pre=[configure], hosts=[GlobalConfig.host], help={'filename': 'An optional filename to deploy to the server'})
def upload(connection: fabric.Connection, filename: typing.Optional[str] = None) -> None:
    def upload_file(file_format: str, file_name: str, destination_path_format='{.project_name}/{}') -> None:
        connection.put(file_format.format(file_name), destination_path_format.format(GlobalConfig, file_name))

    def upload_directory(directory_name: str) -> None:
        execute(connection, f'mkdir -p {GlobalConfig.project_name}/{directory_name}')

        for _root, _directories, files in os.walk(f'src/{directory_name}'):
            for file in files:
                upload_file(f'src/{directory_name}/{{}}', file, f'{{.project_name}}/{directory_name}/{{}}')

    if filename:
        if filename in GlobalConfig.source_directories:
            upload_directory(filename)
        else:
            if filename in GlobalConfig.source_filenames:
                file_path_format = 'src/{}'
            elif filename in GlobalConfig.meta_filenames:
                file_path_format = '{}'
            else:
                raise invoke.ParseError(f'Filename "{filename}" is not registered')

            upload_file(file_path_format, filename)
    else:
        for name in GlobalConfig.source_filenames:
            upload_file('src/{}', name)

        for name in GlobalConfig.meta_filenames:
            upload_file('{}', name)

        for directory in GlobalConfig.source_directories:
            upload_directory(directory)


@fabric.task(pre=[configure], hosts=[GlobalConfig.host], help={'filename': 'An optional filename to deploy to the server'})
def deploy(connection: fabric.Connection, filename: typing.Optional[str] = None) -> None:
    upload(connection, filename)

    with connection.cd(GlobalConfig.project_name):
        execute(connection, 'eval "$(pyenv init --path)" && poetry install --no-dev', {
            'PATH': '$HOME/.pyenv/bin:$HOME/.poetry/bin:$PATH'
        })


@fabric.task(pre=[configure], hosts=[GlobalConfig.host], help={'filename': 'The filename to backup locally from the server'})
def backup(connection: fabric.Connection, filename: str) -> None:
    current_date = datetime.datetime.now().strftime(src.constants.GENERIC_DATE_FORMAT)
    name, extension = os.path.splitext(filename)

    with connection.cd(GlobalConfig.project_name):
        connection.get(f'{GlobalConfig.project_name}/{filename}', f'backup_{name}_{current_date}{extension}')


@fabric.task(pre=[configure], hosts=[GlobalConfig.host])
def backup_db(context: fabric.Connection) -> None:
    backup(context, 'file_convert.sqlite')
