from . import gitlab


GET, POST = gitlab.GET, gitlab.POST


class Pipeline(gitlab.Resource):

    @classmethod
    def pipelines_by_branch(cls, project_id, branch, api):
        pipelines_info = api.call(GET(
            '/projects/{project_id}/pipelines'.format(project_id=project_id),
            {'ref': branch, 'order_by': 'id', 'sort': 'desc'},
        ))

        return [cls(api, pipeline_info) for pipeline_info in pipelines_info]

    @classmethod
    def create(cls, project_id, ref, api):
        try:
            pipeline_info = {}
            api.call(POST(
                '/projects/{project_id}/pipeline'.format(project_id=project_id), {'ref': ref}),
                response_json=pipeline_info
            )
            return cls(api, pipeline_info)
        except gitlab.ApiError:
            return None

    @property
    def ref(self):
        return self.info['ref']

    @property
    def sha(self):
        return self.info['sha']

    @property
    def status(self):
        return self.info['status']

    @property
    def id(self):
        return self.info['id']

    def get_jobs(self, project_id):
        jobs_info = self._api.call(GET(
            '/projects/{project_id}/pipelines/{pipeline_id}/jobs'.format(
                project_id=project_id, pipeline_id=self.id
            )
        ))

        return jobs_info
