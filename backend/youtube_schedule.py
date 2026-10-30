"""Timezone validation and YouTube native schedule operations; never wait until publish time."""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

MIN_LEAD = timedelta(minutes=30)
UPDATE_SCOPE = 'https://www.googleapis.com/auth/youtube.force-ssl'


class Schedule(BaseModel):
    model_config = ConfigDict(extra='forbid')
    local_datetime: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$')
    timezone: str = Field(min_length=1, max_length=100)
    utc_offset_minutes: int | None = Field(default=None, ge=-840, le=840)


def resolve(schedule, now=None, check_lead=True):
    """Reject DST gaps; repeated wall times require an explicit matching UTC offset."""
    try:
        wall = datetime.fromisoformat(schedule.local_datetime)
        zone = ZoneInfo(schedule.timezone)
    except (ValueError, ZoneInfoNotFoundError):
        raise HTTPException(422, 'Choose a valid date, time and IANA timezone.')
    candidates = {}
    for fold in (0, 1):
        local = wall.replace(tzinfo=zone, fold=fold)
        utc = local.astimezone(timezone.utc)
        if utc.astimezone(zone).replace(tzinfo=None) == wall:
            candidates[int(local.utcoffset().total_seconds()/60)] = utc
    if not candidates:
        raise HTTPException(422, 'This local time does not exist because the clocks change. Choose another time.')
    if schedule.utc_offset_minutes is None and len(candidates) > 1:
        raise HTTPException(422, 'This local time occurs twice when the clocks change. Select the first or second occurrence.')
    offset = schedule.utc_offset_minutes if schedule.utc_offset_minutes is not None else next(iter(candidates))
    if offset not in candidates:
        raise HTTPException(422, 'The timezone offset does not match this date and time. Review the timezone and try again.')
    utc = candidates[offset]
    if check_lead and utc < (now or datetime.now(timezone.utc)) + MIN_LEAD:
        raise HTTPException(422, 'Choose a time at least 30 minutes from now to allow uploading and processing. Long videos may need more time.')
    return {**schedule.model_dump(), 'utc_offset_minutes': offset, 'publish_at': utc.isoformat().replace('+00:00', 'Z')}


def validate_lead(schedule):
    if datetime.fromisoformat(schedule['publish_at'].replace('Z', '+00:00')) < datetime.now(timezone.utc)+MIN_LEAD:
        raise HTTPException(409, 'Rendering or processing used the scheduling buffer. Your video remains Private. Choose a new time at least 30 minutes from now.')


def status_payload(remote_status, publish_at=None):
    # videos.update replaces mutable fields in the supplied part. Preserve other settings.
    mutable = ('license', 'embeddable', 'publicStatsViewable', 'selfDeclaredMadeForKids', 'containsSyntheticMedia')
    status = {key: remote_status[key] for key in mutable if key in remote_status}
    status['privacyStatus'] = 'private'
    if publish_at:
        status['publishAt'] = publish_at
    # Omitting publishAt explicitly removes the existing scheduled publication.
    return status


def matches(remote_status, publish_at):
    if remote_status.get('privacyStatus') != 'private':
        return False
    actual = remote_status.get('publishAt')
    if not publish_at:
        return not actual
    try:
        return datetime.fromisoformat(actual.replace('Z', '+00:00')) == datetime.fromisoformat(publish_at.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return False
