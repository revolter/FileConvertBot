import configparser
import datetime
import os
import sys
import typing

import fabric
import invoke
from invoke import env

import src.constants

try:
    config = configparser.ConfigParser()

    config.read('fabfile.cfg')

    env.hosts = [config.get('Fabric', 'Host')]
    env.user = config.get('Fabric', 'User')
    env.key_filename = config.get('Fabric', 'KeyFilename')

    env.project_name = config.get('Fabric', 'ProjectName')
    env.project_path = config.get('Fabric', 'ProjectPath')
except configparser.Error as error:
    print('Config error: {}'.format(error))

    sys.exit(1)

env.source_filenames = [
    'main.py',
    'database.py',
    'utils.py',
    'analytics.py',
    'constants.py',

    'custom_logger.py',

    'config.cfg'
]
env.meta_filenames = [
    'Pipfile',
    'Pipfile.lock'
]
env.source_directories = [
    'migrations'
]


@fabric.task
def configure(context: invoke.Context) -> None:
    context.user = env.user
    context.connect_kwargs.key_filename = os.path.expanduser(env.key_filename)


@fabric.task(pre=[configure], hosts=env.hosts, help={'command': 'The shell command to execute on the server'})
def execute(context: invoke.Context, command: typing.Optional[str] = None) -> None:
    if not command:
        return

    context.run(command)


@fabric.task(pre=[configure], hosts=env.hosts)
def cleanup(context: invoke.Context) -> None:
    prompt_message = 'Are you sure you want to completely delete the project "{0.project_name}" from "{0.hosts[0]}"? y/n: '.format(env)
    response = input(prompt_message)

    if response.lower() == 'y':
        execute(context, 'rm -rf {.project_name}'.format(env))
        execute(context, 'rm -rf {0.project_path}/{0.project_name}'.format(env))


@fabric.task(pre=[configure, cleanup], hosts=env.hosts)
def setup(context: invoke.Context) -> None:
    execute(context, 'mkdir -p {0.project_path}/{0.project_name}'.format(env))
    execute(context, 'ln -s {0.project_path}/{0.project_name} {0.project_name}'.format(env))

    execute(context, 'python -m pip install --user pipenv')


@fabric.task(pre=[configure], hosts=env.hosts, help={'filename': 'An optional filename to deploy to the server'})
def upload(context: invoke.Context, filename: typing.Optional[str] = None) -> None:
    def upload_file(file_format: str, file_name: str, destination_path_format='{.project_name}/{}') -> None:
        context.put(file_format.format(file_name), destination_path_format.format(env, file_name))

    def upload_directory(directory_name: str) -> None:
        execute(context, 'mkdir -p {.project_name}/{}'.format(env, directory_name))

        for _, _, files in os.walk('src/{}'.format(directory_name)):
            for file in files:
                upload_file('src/{}/{{}}'.format(directory_name), file, '{{.project_name}}/{}/{{}}'.format(directory_name))

    if not filename:
        for name in env.source_filenames:
            upload_file('src/{}', name)

        for name in env.meta_filenames:
            upload_file('{}', name)

        for directory in env.source_directories:
            upload_directory(directory)
    else:
        if filename in env.source_directories:
            upload_directory(filename)
        else:
            if filename in env.source_filenames:
                file_path_format = 'src/{}'
            elif filename in env.meta_filenames:
                file_path_format = '{}'
            else:
                print('Filename "{}" is not registered'.format(filename))

                sys.exit(2)

            upload_file(file_path_format, filename)


@fabric.task(pre=[configure], hosts=env.hosts, help={'filename': 'An optional filename to deploy to the server'})
def deploy(context: invoke.Context, filename: typing.Optional[str] = None) -> None:
    upload(context, filename)

    with context.cd(env.project_name):
        execute(context, 'python -m pipenv install --three')


@fabric.task(pre=[configure], hosts=env.hosts, help={'filename': 'The filename to backup locally from the server'})
def backup(context: invoke.Context, filename: str) -> None:
    current_date = datetime.datetime.now().strftime(src.constants.GENERIC_DATE_FORMAT)
    name, extension = os.path.splitext(filename)

    # This currently does nothing: http://www.fabfile.org/upgrading.html?highlight=cd#actual-remote-steps.
    with context.cd(env.project_name):
        context.get('{.project_name}/{}'.format(env, filename), 'backup_{}_{}{}'.format(name, current_date, extension))


@fabric.task(pre=[configure], hosts=env.hosts)
def backup_db(context: invoke.Context) -> None:
    backup(context, 'file_convert.sqlite')
