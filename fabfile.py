from datetime import datetime

import configparser
import os
import sys

from fabric import task
from invoke import env

from src.constants import GENERIC_DATE_FORMAT

try:
    config = configparser.ConfigParser()

    config.read('fabfile.cfg')

    env.hosts = [config.get('Fabric', 'Host')]
    env.user = config.get('Fabric', 'User')
    env.key_filename = config.get('Fabric', 'KeyFilename')

    env.project_path = config.get('Fabric', 'ProjectPath')
except configparser.Error as error:
    print('Config error: {}'.format(error))

    sys.exit(1)

env.project_name = 'FileConvertBot'
env.source_filenames = [
    'main.py',
    'database.py',
    'utils.py',
    'analytics.py',
    'constants.py',

    'config.cfg'
]
env.meta_filenames = [
    'Pipfile',
    'Pipfile.lock'
]
env.source_directories = [
    'migrations'
]


@task
def config(context):
    context.user = env.user
    context.connect_kwargs.key_filename = os.path.expanduser(env.key_filename)


@task(pre=[config], hosts=env.hosts, help={'command': 'The shell command to execute on the server'})
def execute(context, command=None):
    if not command:
        return

    context.run(command)


@task(pre=[config], hosts=env.hosts)
def cleanup(context):
    prompt_message = 'Are you sure you want to completely delete the project "{0.project_name}" from "{0.hosts[0]}"? y/n: '.format(env)
    response = input(prompt_message)

    if response.lower() == 'y':
        execute(context, 'rm -rf {.project_name}'.format(env))
        execute(context, 'rm -rf {0.project_path}/{0.project_name}'.format(env))


@task(pre=[config, cleanup], hosts=env.hosts)
def setup(context):
    execute(context, 'mkdir -p {0.project_path}/{0.project_name}'.format(env))
    execute(context, 'ln -s {0.project_path}/{0.project_name} {0.project_name}'.format(env))

    execute(context, 'python -m pip install --user pipenv')


@task(pre=[config], hosts=env.hosts, help={'type': 'The type of the file to be deployed. Only required if `filename` is specified. Valid values are `source` and `meta`.', 'filename': 'An optional filename to deploy to the server'})
def deploy(context, type='source', filename=None):
    if not type or not filename:
        for filename in env.source_filenames:
            context.put('src/{}'.format(filename), '{.project_name}/'.format(env))

        for filename in env.meta_filenames:
            context.put(filename, '{.project_name}/'.format(env))

        for directory in env.source_directories:
            execute(context, 'mkdir -p {.project_name}/{}'.format(env, directory))

            for _, _, files in os.walk('src/{}'.format(directory)):
                for file in files:
                    context.put('src/{}/{}'.format(directory, file), '{.project_name}/{}/{}'.format(env, directory, file))

        with context.cd(env.project_name):
            execute(context, 'python -m pipenv install --three')
    else:
        file_path_format = 'src/{}' if type == 'source' else '{}'

        context.put(file_path_format.format(filename), '{.project_name}/'.format(env))


@task(pre=[config], hosts=env.hosts, help={'filename': 'The filename to backup locally from the server'})
def backup(context, filename):
    current_date = datetime.now().strftime(GENERIC_DATE_FORMAT)
    name, extension = os.path.splitext(filename)

    # This currently does nothing: http://www.fabfile.org/upgrading.html?highlight=cd#actual-remote-steps.
    with context.cd(env.project_name):
        context.get('{.project_name}/{}'.format(env, filename), 'backup_{}_{}{}'.format(name, current_date, extension))


@task(pre=[config], hosts=env.hosts)
def backup_db(context):
    backup(context, 'file_convert.sqlite')
