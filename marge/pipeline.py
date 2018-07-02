from . import gitlab


GET, POST = gitlab.GET, gitlab.POST


class Pipeline(gitlab.Resource):
    def __init__(self, api, info, project_id):
        info['project_id'] = project_id
        super().__init__(api, info)

    @classmethod
    def pipelines_by_branch(
            cls, project_id, branch, api, *,
            ref=None,
            status=None,
            order_by='id',
            sort='desc',
    ):
        params = {
            'ref': branch if ref is None else ref,
            'order_by': order_by,
            'sort': sort,
        }
        if status is not None:
            params['status'] = status
        pipelines_info = api.call(GET(
            '/projects/{project_id}/pipelines'.format(project_id=project_id),
            params,
        ))

        return [cls(api, pipeline_info, project_id) for pipeline_info in pipelines_info]

    @classmethod
    def create(cls, project_id, ref, api):
        try:
            pipeline_info = {}
            api.call(POST(
                '/projects/{project_id}/pipeline'.format(project_id=project_id), {'ref': ref}),
                response_json=pipeline_info
            )
            return cls(api, pipeline_info, project_id)
        except gitlab.ApiError:
            return None

    @property
    def project_id(self):
        return self.info['project_id']

    @property
    def id(self):
        return self.info['id']

    @property
    def status(self):
        return self.info['status']

    @property
    def ref(self):
        return self.info['ref']

    @property
    def sha(self):
        return self.info['sha']

    def cancel(self):
        return self._api.call(POST(
            '/projects/{0.project_id}/pipelines/{0.id}/cancel'.format(self),
        ))

    def get_jobs(self):
        jobs_info = self._api.call(GET(
            '/projects/{0.project_id}/pipelines/{0.id}/jobs'.format(self),
        ))

        return jobs_info
