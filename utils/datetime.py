"""UTCで保存された日時を画面表示用の日本時間へ変換する。"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


UTC = timezone.utc
JST = ZoneInfo("Asia/Tokyo")


def _parse_datetime(value):
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("日時が指定されていません")

    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(text, pattern)
            except ValueError:
                continue
    raise ValueError(f"対応していない日時形式です: {value}")


def to_jst(value):
    """datetimeまたはUTC日時文字列をAsia/Tokyoのaware datetimeへ変換する。"""
    parsed = _parse_datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(JST)


def format_datetime(value, pattern="%Y-%m-%d %H:%M"):
    """日時をJSTへ変換して表示する。不正値は画面を壊さず元の値を返す。"""
    if value is None or value == "":
        return ""
    try:
        return to_jst(value).strftime(pattern)
    except (TypeError, ValueError, OverflowError):
        return str(value)


def utc_now_string():
    """DB保存用の現在UTC日時をタイムゾーンなし文字列で返す。"""
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
