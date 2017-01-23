import datetime
import operator
from enum import Enum, unique

import maya


@unique
class WeekDay(Enum):
    Monday = 0
    Tuesday = 1
    Wednesday = 2
    Thursday = 3
    Friday = 4
    Saturday = 5
    Sunday = 6


_day_names = { day.name.lower(): day for day in WeekDay }
_day_names.update((day.name.lower()[:3], day) for day in WeekDay)
_day_names.update((day, day) for day in WeekDay)


def find_weekday(string_or_day):
    if isinstance(string_or_day, WeekDay):
        return string_or_day

    if isinstance(string_or_day, str):
        return _day_names[string_or_day.lower()]

    raise ValueError('Not a week day: %r' % string_or_day)


time = datetime.time

class WeeklyInterval(object):
    def __init__(self, from_weekday, from_time, to_weekday, to_time):
        from_weekday = find_weekday(from_weekday)
        to_weekday = find_weekday(to_weekday)

        # the class invariant is that from_weekday <= to_weekday; so when this
        # is not the case (e.g. a Fri-Mon interval), we store the complement interval
        # (in the example, Mon-Fri), and invert the criterion
        self._is_complement_interval = from_weekday.value > to_weekday.value
        if self._is_complement_interval:
            self._from_weekday = to_weekday
            self._from_time = to_time
            self._to_weekday = from_weekday
            self._to_time = from_time
        else:
            self._from_weekday = from_weekday
            self._from_time = from_time
            self._to_weekday = to_weekday
            self._to_time = to_time

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        return False

    def __ne__(self, other):
        return not self == other


    @classmethod
    def from_human(cls, string):
        from_,to_ = string.split('-')

        def parse_part(part):
            part = part.replace('@', ' ')
            weekday, time = part.split()
            weekday = find_weekday(weekday)
            time = maya.parse(time).datetime().time()
            return weekday, time

        from_weekday, from_time = parse_part(from_)
        to_weekday, to_time = parse_part(to_)
        return cls(from_weekday, from_time, to_weekday, to_time)




    def covers(self, date):
        return self._interval_covers(date) != self._is_complement_interval


    def _interval_covers(self, date):
        weekday = date.date().weekday()
        time = date.time()
        before = operator.le if self._is_complement_interval else operator.lt

        if not (self._from_weekday.value <= weekday <= self._to_weekday.value):
            return False

        if self._from_weekday.value == weekday and before(time, self._from_time):
            return False

        if self._to_weekday.value == weekday and before(self._to_time, time):
            return False

        return True

