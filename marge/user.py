from . import gitlab


GET = gitlab.GET


class User(gitlab.Resource):

    @classmethod
    def myself(cls, api, sudo=None):
        return cls(api, api.call(GET('/user'), sudo=sudo))

    @property
    def is_admin(self):
        return self.info.get('is_admin')

    @classmethod
    def fetch_by_id(cls, user_id, api):
        info = api.call(GET('/users/%s' % user_id))
        return cls(api, info)

    @classmethod
    def fetch_by_username(cls, username, api):
        info = api.call(GET(
            '/users',
            {'username': username},
            gitlab.from_singleton_list(),
        ))
        return cls(api, info)

    @property
    def name(self):
        return self.info['name'].strip()

    @property
    def username(self):
        return self.info['username']

    @property
    def email(self):
        """Only visible to admins and 'self'. Sigh."""
        return self.info.get('email')

    @property
    def state(self):
        return self.info['state']
