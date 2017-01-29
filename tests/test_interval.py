from datetime import time

import maya
from marge.interval import WeeklyInterval

def date(spec):
    return maya.parse(spec).datetime()


class TestWeekly(object):
    def test_on_same_week(self):
        interval = WeeklyInterval('Mon', time(10, 00), 'Fri', time(18, 00))
        assert interval.covers(date('Tuesday 3pm'))
        assert not interval.covers(date('Sunday 5pm'))

        assert interval.covers(date('Monday 10am'))
        assert not interval.covers(date('Monday 9:59am'))

        assert interval.covers(date('Friday 6pm'))
        assert not interval.covers(date('Friday 6:01pm'))

    def test_span_two_weeks(self):
        interval = WeeklyInterval('Friday', time(12, 00), 'Mon', time(7, 00))
        assert interval.covers(date('Sunday 10am'))
        assert not interval.covers(date('Wed 10am'))

        assert interval.covers(date('Friday 12:00pm'))
        assert not interval.covers(date('Friday 11:59am'))

        assert interval.covers(date('Monday 7am'))
        assert not interval.covers(date('Monday 7:01am'))

    def test_from_human(self):
        working_hours = WeeklyInterval('Mon', time(9, 00), 'Fri', time(17, 0))

        assert WeeklyInterval.from_human('Mon@9am - Fri@5pm') == working_hours
        assert WeeklyInterval.from_human('Monday 9:00 - Friday@17:00') == working_hours
        assert WeeklyInterval.from_human('Mon@9:00-Fri@17:00') == working_hours
        assert not WeeklyInterval.from_human('Mon@9:00-Tue@17:00') == working_hours
