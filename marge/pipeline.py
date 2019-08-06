import logging as log

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
    def pipelines_by_merge_request(cls, project_id, merge_request_iid, api):
        """Fetch all pipelines for a merge request in descending order of pipeline ID."""
        pipelines_info = api.call(GET(
            '/projects/{project_id}/merge_requests/{merge_request_iid}/pipelines'.format(
                project_id=project_id, merge_request_iid=merge_request_iid,
            )
        ))
        pipelines_info.sort(key=lambda pipeline_info: pipeline_info['id'], reverse=True)
        return [cls(api, pipeline_info, project_id) for pipeline_info in pipelines_info]

    @classmethod
    def manual_jobs_by_pipeline(cls, project_id, pipeline_id, api):
        jobs = api.call(
            GET('/projects/{project_id}/pipelines/{pipeline_id}/jobs?scope[]=manual'.format(
                project_id=project_id, pipeline_id=pipeline_id)
            )
        )
        return jobs

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
