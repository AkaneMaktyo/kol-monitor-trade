"""Normalize WxPusher log entries for signal parsing."""

import re

from app.signals.models import NormalizedMessage


SOURCE_LABELS = ("原文:", "source:", "Source:")
DETAIL_LABELS = ("详情:", "detail:", "Detail:")


def normalize_entry(entry: dict, detail_text: str = "") -> NormalizedMessage:
    raw_text = detail_text.strip() or entry.get("content", "")
    content = entry.get("content", "")
    source_url = _extract_labeled_url(content, SOURCE_LABELS)
    detail_url = _extract_labeled_url(content, DETAIL_LABELS)
    main_text = _clean_body(raw_text)
    return NormalizedMessage(
        log_id=entry.get("id", ""),
        timestamp=entry.get("timestamp", ""),
        raw_text=raw_text,
        main_text=main_text,
        source_url=source_url,
        detail_url=detail_url,
        source_channel=entry.get("source_channel", ""),
        author=entry.get("author", ""),
        dedupe_key=source_url or detail_url or entry.get("id", ""),
        detail_fetched=bool(detail_text.strip()),
    )


def detail_url(entry: dict) -> str:
    return _extract_labeled_url(entry.get("content", ""), DETAIL_LABELS)


def is_gold_empire(entry: dict) -> bool:
    content = entry.get("content", "")
    return "黄金帝国" in content or "PREMIUM SIGNALS" in content and "MANSOOR" not in content


def _extract_labeled_url(text: str, labels: tuple[str, ...]) -> str:
    for line in text.splitlines():
        line = line.strip()
        for label in labels:
            if line.startswith(label):
                return line.split(":", 1)[1].strip()
    match = re.search(r"https://[^\s]+", text)
    return match.group(0) if match else ""


def _clean_body(text: str) -> str:
    lines = []
    for line in text.splitlines():
        clean = line.strip()
        if not clean or _noise(clean):
            continue
        clean = re.sub(r"^\[[^\]]+\]\s*", "", clean)
        clean = re.sub(r"^PREMIUM SIGNALS:\s*", "", clean, flags=re.I)
        if clean:
            lines.append(clean)
    return "\n".join(lines)


def _noise(line: str) -> bool:
    if line.startswith(("原文:", "详情:", "Embeds", "图片", "[图片:")):
        return True
    if line.startswith("您订阅的"):
        return True
    if line in {"PREMIUM SIGNALS", "Discord -> WxPusher"}:
        return True
    return bool(re.match(r"^\d{4}[-/年]", line))
