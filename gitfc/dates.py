import re
import sys
from datetime import datetime, timedelta


# check if a date string matches any of our expected formats
def validate_date(date_str):
    formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]
    for fmt in formats:
        try:
            datetime.strptime(date_str, fmt)
            return True
        except ValueError:
            continue
    return False


# turn stuff like "+15m", "14:30", or "2026-04-01" into a proper datetime string
def parse_date(value):
    now = datetime.now()

    if value is None:
        return now.strftime("%Y-%m-%d %H:%M:%S")

    # relative offset like +15m, -2h, +3d
    match = re.fullmatch(r"([+-]\d+)([mhd])", value)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        delta = {"m": timedelta(minutes=amount), "h": timedelta(hours=amount), "d": timedelta(days=amount)}[unit]
        return (now + delta).strftime("%Y-%m-%d %H:%M:%S")

    # just a time like "14:30" (assume today)
    if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", value):
        return f"{now.strftime('%Y-%m-%d')} {value}"

    if not validate_date(value):
        print(f'Error: invalid date format "{value}"', file=sys.stderr)
        print('Expected: "+15m", "-2d", "14:30", "2026-04-01", or "2026-04-01 14:30:00"', file=sys.stderr)
        sys.exit(1)

    return value


def parse_duration(value):
    match = re.fullmatch(r"(\d+)([mhd])", value)
    if not match:
        print(f'Error: invalid duration "{value}"', file=sys.stderr)
        print('Expected: "10m", "2h", "1d"', file=sys.stderr)
        sys.exit(1)
    amount = int(match.group(1))
    unit = match.group(2)
    return {"m": 60, "h": 3600, "d": 86400}[unit] * amount


def format_relative(dt_str):
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    diff = dt - datetime.now()
    total_sec = int(diff.total_seconds())

    if abs(total_sec) < 60:
        return "now"

    future = total_sec > 0
    total_sec = abs(total_sec)

    if total_sec < 3600:
        val = total_sec // 60
        unit = "m"
    elif total_sec < 86400:
        val = total_sec // 3600
        unit = "h"
    else:
        val = total_sec // 86400
        unit = "d"

    return f"in {val}{unit}" if future else f"{val}{unit} ago"
