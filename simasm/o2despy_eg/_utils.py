import datetime as dt


def timedelta2hours(timedelta):
    """ Convert datetime.timedelta to total hours.

    Args:
        timedelta: datetime.timedelta.

    Returns:
        total hours.

    Raises:
        ZeroDivisionError: an error occurred when division by 0.
    """
    try:
        return timedelta.total_seconds() / float(3600)
    except ZeroDivisionError as e:
        raise e
