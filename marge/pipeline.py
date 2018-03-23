from . import gitlab


GET = gitlab.GET


class Pipeline(gitlab.Resource):

    @classmethod
    def pipelines_by_branch(cls, project_id, branch, api):
        pipelines_info = api.call(GET(
            '/projects/{project_id}/pipelines'.format(project_id=project_id),
            {'ref': branch, 'order_by': 'id', 'sort': 'desc'},
        ))

        return [cls(api, pipeline_info) for pipeline_info in pipelines_info]

    @property
    def ref(self):
        return self.info['ref']

    @property
    def sha(self):
        return self.info['sha']

    @property
    def status(self):
        return self.info['status']
