GENERIC_DATE_TIME_FORMAT = '%Y-%m-%d %H:%M:%S'


def migrate(migrator, database, fake=False, **kwargs):
    if fake is True:
        return

    User = migrator.orm['user']

    for user in User.select():
        user.created_at = user.created_at.strftime(GENERIC_DATE_TIME_FORMAT)
        user.updated_at = user.updated_at.strftime(GENERIC_DATE_TIME_FORMAT)

        user.save()
