import marge.gitlab as gitlab


class TestVersion(object):
    def test_parse(self):
        assert gitlab.Version.parse('9.2.2-ee') == gitlab.Version(release=(9, 2, 2), edition='ee')

    def test_parse_no_edition(self):
        assert gitlab.Version.parse('9.4.0')  == gitlab.Version(release=(9, 4, 0), edition=None)
