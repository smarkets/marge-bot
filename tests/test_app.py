import datetime

from marge.app import time_interval


# FIXME: I'd reallly prefer this to be a doctest, but adding --doctest-modules
# seems to seriously mess up the test run
def test_time_interval():
    _900s = datetime.timedelta(0, 900)
    assert [time_interval(x) for x in ['15min', '15min', '.25h', '900s']] == [_900s] * 4
