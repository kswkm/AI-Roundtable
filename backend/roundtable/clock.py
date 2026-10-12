from datetime import UTC, datetime


def utcnow() -> datetime:
    """naive UTC. SQLite가 시간대를 저장하지 않으므로 앱 전체에서 naive UTC로 통일한다."""
    return datetime.now(UTC).replace(tzinfo=None)
