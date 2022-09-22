import unittest
import os

import marge.gitlab as gitlab
from marge.gitlab import GET

HTTPBIN = (
    os.environ["HTTPBIN_URL"] if "HTTPBIN_URL" in os.environ else "https://httpbin.org"
)


class TestVersion:
    def test_parse(self):
        assert gitlab.Version.parse('9.2.2-ee') == gitlab.Version(release=(9, 2, 2), edition='ee')

    def test_parse_no_edition(self):
        assert gitlab.Version.parse('9.4.0') == gitlab.Version(release=(9, 4, 0), edition=None)

    def test_is_ee(self):
        assert gitlab.Version.parse('9.4.0-ee').is_ee
        assert not gitlab.Version.parse('9.4.0').is_ee


class TestApiCalls(unittest.TestCase):
    def test_success_immediately_no_response(self):
        api = gitlab.Api(HTTPBIN, "", append_api_version=False)
        self.assertTrue(api.call(GET("/status/202")))
        self.assertTrue(api.call(GET("/status/204")))
        self.assertFalse(api.call(GET("/status/304")))

    def test_failure_after_all_retries(self):
        api = gitlab.Api(HTTPBIN, "", append_api_version=False)

        with self.assertRaises(gitlab.Conflict):
            api.call(GET("/status/409"))

        with self.assertRaises(gitlab.TooManyRequests):
            api.call(GET("/status/429"))

        with self.assertRaises(gitlab.GatewayTimeout):
            api.call(GET("/status/504"))
