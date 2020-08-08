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
        'analytics.py',
        'constants.py',

        'custom_logger.py',

        'config.cfg'
    ]
    meta_filenames = [
        'Pipfile',
        'Pipfile.lock'
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
                message='Config error: {}'.format(error),
                code=1
            )


invoke_patch.fix_annotations()
GlobalConfig.load()


@fabric.task
def configure(connection: fabric.Connection) -> None:
    connection.user = GlobalConfig.user
    connection.connect_kwargs.key_filename = GlobalConfig.key_filename


@fabric.task(pre=[configure], hosts=[GlobalConfig.host], help={'command': 'The shell command to execute on the server'})
def execute(connection: fabric.Connection, command: typing.Optional[str] = None) -> None:
    if not command:
        return

    connection.run(command)


@fabric.task(pre=[configure], hosts=[GlobalConfig.host])
def cleanup(connection: fabric.Connection) -> None:
    question = 'Are you sure you want to completely delete the project "{0.project_name}" from "{0.host}"?'.format(GlobalConfig)

    if invocations.console.confirm(
        question=question,
        assume_yes=False
    ):
        execute(connection, 'rm -rf {.project_name}'.format(GlobalConfig))
        execute(connection, 'rm -rf {0.project_path}/{0.project_name}'.format(GlobalConfig))


@fabric.task(pre=[configure, cleanup], hosts=[GlobalConfig.host])
def setup(connection: fabric.Connection) -> None:
    execute(connection, 'mkdir -p {0.project_path}/{0.project_name}'.format(GlobalConfig))
    execute(connection, 'ln -s {0.project_path}/{0.project_name} {0.project_name}'.format(GlobalConfig))

    execute(connection, 'python -m pip install --user pipenv')


@fabric.task(pre=[configure], hosts=[GlobalConfig.host], help={'filename': 'An optional filename to deploy to the server'})
def upload(connection: fabric.Connection, filename: typing.Optional[str] = None) -> None:
    def upload_file(file_format: str, file_name: str, destination_path_format: str = '{.project_name}/{}') -> None:
        connection.put(file_format.format(file_name), destination_path_format.format(GlobalConfig, file_name))

    def upload_directory(directory_name: str) -> None:
        execute(connection, 'mkdir -p {.project_name}/{}'.format(GlobalConfig, directory_name))

        for _root, _directories, files in os.walk('src/{}'.format(directory_name)):
            for file in files:
                upload_file('src/{}/{{}}'.format(directory_name), file, '{{.project_name}}/{}/{{}}'.format(directory_name))

    if not filename:
        for name in GlobalConfig.source_filenames:
            upload_file('src/{}', name)

        for name in GlobalConfig.meta_filenames:
            upload_file('{}', name)

        for directory in GlobalConfig.source_directories:
            upload_directory(directory)
    else:
        if filename in GlobalConfig.source_directories:
            upload_directory(filename)
        else:
            if filename in GlobalConfig.source_filenames:
                file_path_format = 'src/{}'
            elif filename in GlobalConfig.meta_filenames:
                file_path_format = '{}'
            else:
                raise invoke.ParseError('Filename "{}" is not registered'.format(filename))

            upload_file(file_path_format, filename)


@fabric.task(pre=[configure], hosts=[GlobalConfig.host], help={'filename': 'An optional filename to deploy to the server'})
def deploy(connection: fabric.Connection, filename: typing.Optional[str] = None) -> None:
    upload(connection, filename)

    with connection.cd(GlobalConfig.project_name):
        execute(connection, 'python -m pipenv install --three')


@fabric.task(pre=[configure], hosts=[GlobalConfig.host], help={'filename': 'The filename to backup locally from the server'})
def backup(connection: fabric.Connection, filename: str) -> None:
    current_date = datetime.datetime.now().strftime(src.constants.GENERIC_DATE_FORMAT)
    name, extension = os.path.splitext(filename)

    with connection.cd(GlobalConfig.project_name):
        connection.get('{.project_name}/{}'.format(GlobalConfig, filename), 'backup_{}_{}{}'.format(name, current_date, extension))


@fabric.task(pre=[configure], hosts=[GlobalConfig.host])
def backup_db(context: fabric.Connection) -> None:
    backup(context, 'file_convert.sqlite')
