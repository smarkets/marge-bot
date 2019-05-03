from unittest.mock import Mock

from marge.gitlab import Api, GET
from marge.pipeline import Pipeline


INFO = {
    "id": 47,
    "status": "pending",
    "ref": "new-pipeline",
    "sha": "a91957a858320c0e17f3a0eca7cfacbff50ea29a"
}


# pylint: disable=attribute-defined-outside-init
class TestPipeline:

    def setup_method(self, _method):
        self.api = Mock(Api)

    def test_pipelines_by_branch(self):
        api = self.api
        pl1, pl2 = INFO, dict(INFO, id=48)
        api.call = Mock(return_value=[pl1, pl2])

        result = Pipeline.pipelines_by_branch(project_id=1234, branch=INFO['ref'], api=api)
        api.call.assert_called_once_with(GET(
            '/projects/1234/pipelines',
            {'ref': INFO['ref'], 'order_by': 'id', 'sort': 'desc'},
        ))
        assert [pl.info for pl in result] == [pl1, pl2]

    def test_properties(self):
        pipeline = Pipeline(api=self.api, project_id=1234, info=INFO)
        assert pipeline.id == 47
        assert pipeline.project_id == 1234
        assert pipeline.status == "pending"
        assert pipeline.ref == "new-pipeline"
        assert pipeline.sha == "a91957a858320c0e17f3a0eca7cfacbff50ea29a"
