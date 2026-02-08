import json
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Iterable

import requests
import xml.etree.ElementTree as ET

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ai_products.json")
SOURCES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ai_sources.json")
RSS_SOURCES = {
    "product_hunt": "https://www.producthunt.com/feed"
}
ZAPIER_AI_LIST_URL = "https://zapier.com/blog/best-ai-productivity-tools/"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


def _parse_rss(url: str) -> list[dict]:
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return []
        root = ET.fromstring(response.text)
        items = []
        for item in root.findall(".//item"):
            title = _strip_html(item.findtext("title", default=""))
            link = item.findtext("link", default="")
            description = _strip_html(item.findtext("description", default=""))
            pub_date = item.findtext("pubDate", default="")
            items.append({
                "title": title,
                "link": link,
                "description": description,
                "pub_date": pub_date
            })
        return items
    except Exception:
        return []


def _parse_zapier_ai_list(html: str) -> list[str]:
    if not html:
        return []
    # Try to capture product names from headings like "### **Zapier**"
    matches = re.findall(r"<h3[^>]*>\\s*(?:<strong>)?([^<]{2,80})(?:</strong>)?\\s*</h3>", html, re.IGNORECASE)
    cleaned = []
    for m in matches:
        name = _strip_html(m)
        if name and name not in cleaned:
            cleaned.append(name)
    return cleaned


def _parse_generic_product_list(html: str) -> list[str]:
    if not html:
        return []
    # Try to capture product names from headings or strong tags
    candidates = re.findall(r"<h2[^>]*>\\s*(?:<strong>)?([^<]{2,80})(?:</strong>)?\\s*</h2>", html, re.IGNORECASE)
    candidates += re.findall(r"<h3[^>]*>\\s*(?:<strong>)?([^<]{2,80})(?:</strong>)?\\s*</h3>", html, re.IGNORECASE)
    candidates += re.findall(r"<strong>\\s*([^<]{2,80})\\s*</strong>", html, re.IGNORECASE)
    cleaned = []
    for m in candidates:
        name = _strip_html(m)
        if name and len(name.split()) <= 6 and name not in cleaned:
            cleaned.append(name)
    return cleaned


def _slug_to_title(slug: str) -> str:
    slug = slug.strip("/").replace("-", " ")
    return " ".join(word.capitalize() for word in slug.split())


def _extract_tools_from_directory(html: str, path_segment: str = "/tool/") -> list[str]:
    if not html:
        return []
    names = []
    # Anchor text for tool links
    anchor_pattern = re.compile(
        r'<a[^>]+href="[^"]*' + re.escape(path_segment) + r'[^"]*"[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL
    )
    for match in anchor_pattern.findall(html):
        text = _strip_html(match)
        if text and text not in names:
            names.append(text)
    # Fallback: extract slugs from tool links
    slug_pattern = re.compile(r'href="[^"]*' + re.escape(path_segment) + r'([^"#?/]+)', re.IGNORECASE)
    for match in slug_pattern.findall(html):
        title = _slug_to_title(match)
        if title and title not in names:
            names.append(title)
    return names


def _infer_tags(text: str) -> list[str]:
    t = text.lower()
    tags = []
    if any(k in t for k in ["image", "design", "art"]):
        tags.append("image")
    if any(k in t for k in ["video", "editing", "film"]):
        tags.append("video")
    if any(k in t for k in ["code", "developer", "coding"]):
        tags.append("developer")
    if any(k in t for k in ["search", "research"]):
        tags.append("research")
    if any(k in t for k in ["assistant", "chat"]):
        tags.append("assistant")
    if "llm" in t or "language model" in t:
        tags.append("llm")
    if "ai" in t:
        tags.append("ai")
    return list(dict.fromkeys(tags))[:6]


def _normalize_entry(entry: dict, source: str) -> dict | None:
    title = (entry.get("title") or "").strip()
    if not title:
        return None
    summary = (entry.get("description") or "").strip()
    return {
        "name": title,
        "summary": summary or "AI product update from public feeds.",
        "value_proposition": summary or "AI product update from public feeds.",
        "category": "AI Product",
        "pricing": "Unknown",
        "features": [],
        "website_url": entry.get("link") or "",
        "video_url": "",
        "tags": _infer_tags(f"{title} {summary}"),
        "last_updated": _now_iso(),
        "source": source
    }


def _normalize_name_entry(name: str, source: str) -> dict | None:
    title = (name or "").strip()
    if not title:
        return None
    return {
        "name": title,
        "summary": "Listed as a leading AI productivity tool.",
        "value_proposition": "Highlighted in industry lists as a top AI tool.",
        "category": "AI Productivity",
        "pricing": "Unknown",
        "features": [],
        "website_url": "",
        "video_url": "",
        "tags": _infer_tags(title),
        "last_updated": _now_iso(),
        "source": source,
        "source_url": ""
    }


def _default_products() -> dict:
    now = _now_iso()
    return {
        "generated_at": now,
        "source": "manual_seed",
        "sources": ["manual_seed"],
        "products": [
            {
                "name": "ChatGPT",
                "summary": "Conversational AI assistant for writing, analysis, coding, and ideation.",
                "value_proposition": "Speeds up research, drafting, and problem solving across teams.",
                "category": "Assistant",
                "pricing": "Free and paid tiers",
                "features": [
                    "Natural language chat",
                    "Code generation",
                    "File and document analysis"
                ],
                "website_url": "https://chat.openai.com",
                "video_url": "https://www.youtube.com/watch?v=JTxsNm9IdYU",
                "tags": ["productivity", "writing", "coding"],
                "last_updated": now,
                "source": "manual_seed"
            },
            {
                "name": "Claude",
                "summary": "AI assistant focused on long-context reasoning and safety.",
                "value_proposition": "Handles large documents and complex reasoning tasks reliably.",
                "category": "Assistant",
                "pricing": "Free and paid tiers",
                "features": [
                    "Long context analysis",
                    "Structured outputs",
                    "Strong safety alignment"
                ],
                "website_url": "https://claude.ai",
                "video_url": "https://www.youtube.com/watch?v=Z3bTQ0i2lQ4",
                "tags": ["analysis", "research", "writing"],
                "last_updated": now,
                "source": "manual_seed"
            },
            {
                "name": "Midjourney",
                "summary": "Text-to-image generator for high-quality creative visuals.",
                "value_proposition": "Rapidly produces concept art and marketing visuals.",
                "category": "Design",
                "pricing": "Paid tiers",
                "features": [
                    "Text-to-image generation",
                    "Style control",
                    "Upscaling options"
                ],
                "website_url": "https://www.midjourney.com",
                "video_url": "https://www.youtube.com/watch?v=2D6ZQyQ0QyM",
                "tags": ["design", "image", "creative"],
                "last_updated": now,
                "source": "manual_seed"
            },
            {
                "name": "Perplexity",
                "summary": "Answer engine that cites sources for research queries.",
                "value_proposition": "Improves research speed with sourced responses.",
                "category": "Search",
                "pricing": "Free and paid tiers",
                "features": [
                    "Cited answers",
                    "Research collections",
                    "Multi-step query refinement"
                ],
                "website_url": "https://www.perplexity.ai",
                "video_url": "https://www.youtube.com/watch?v=H0M7vVd4jYg",
                "tags": ["search", "research", "citations"],
                "last_updated": now,
                "source": "manual_seed"
            },
            {
                "name": "Runway",
                "summary": "AI video creation and editing toolkit.",
                "value_proposition": "Enables fast video generation and editing for teams.",
                "category": "Video",
                "pricing": "Free and paid tiers",
                "features": [
                    "Text-to-video",
                    "Video editing tools",
                    "Background removal"
                ],
                "website_url": "https://runwayml.com",
                "video_url": "https://www.youtube.com/watch?v=7rYj3rQ3l3g",
                "tags": ["video", "creative", "editing"],
                "last_updated": now,
                "source": "manual_seed"
            },
            {
                "name": "GitHub Copilot",
                "summary": "AI coding assistant embedded in editors.",
                "value_proposition": "Speeds up coding by suggesting code and tests.",
                "category": "Developer",
                "pricing": "Paid tiers",
                "features": [
                    "Inline code suggestions",
                    "Chat-based code help",
                    "Multi-language support"
                ],
                "website_url": "https://github.com/features/copilot",
                "video_url": "https://www.youtube.com/watch?v=6tJxJd3sQdE",
                "tags": ["coding", "developer", "productivity"],
                "last_updated": now,
                "source": "manual_seed"
            }
        ]
    }


def load_ai_products() -> dict:
    if not os.path.exists(DATA_PATH):
        return _default_products()
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Clean out non-product articles from legacy HN feeds.
        cleaned = []
        for item in data.get("products", []):
            source = (item.get("source") or "").lower()
            summary = (item.get("summary") or "").lower()
            if source.startswith("hn_") or "article url:" in summary:
                continue
            cleaned.append(item)
        data["products"] = cleaned
        return data
    except Exception:
        return _default_products()


def save_ai_products(payload: dict) -> None:
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_ai_sources() -> list[dict]:
    if not os.path.exists(SOURCES_PATH):
        return []
    try:
        with open(SOURCES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("sources", [])
    except Exception:
        return []


def _merge_products(existing: Iterable[dict], incoming: Iterable[dict]) -> list[dict]:
    merged = {}
    for item in existing:
        key = (item.get("name") or "").strip().lower()
        if key:
            merged[key] = item
    for item in incoming:
        key = (item.get("name") or "").strip().lower()
        if key and key not in merged:
            merged[key] = item
    return list(merged.values())


def _filter_existing_products(existing: Iterable[dict], allowed_sources: set[str]) -> list[dict]:
    filtered = []
    for item in existing:
        source = item.get("source") or ""
        if not source or source in allowed_sources:
            filtered.append(item)
    return filtered


def sync_ai_products() -> dict:
    current = load_ai_products()
    incoming = []
    for source, url in RSS_SOURCES.items():
        for item in _parse_rss(url):
            normalized = _normalize_entry(item, source)
            if normalized:
                incoming.append(normalized)

    allowed_sources = {"manual_seed"} | set(RSS_SOURCES.keys())
    existing = _filter_existing_products(current.get("products", []), allowed_sources)
    products = _merge_products(existing, incoming)
    payload = {
        "generated_at": _now_iso(),
        "source": "rss_sync",
        "sources": ["manual_seed"] + list(RSS_SOURCES.keys()),
        "products": products
    }
    save_ai_products(payload)
    return payload


def sync_ai_products_zapier() -> dict:
    current = load_ai_products()
    try:
        response = requests.get(ZAPIER_AI_LIST_URL, timeout=12)
        if response.status_code != 200:
            raise RuntimeError("Zapier list fetch failed")
        names = _parse_zapier_ai_list(response.text)
    except Exception:
        names = []

    incoming = []
    for name in names:
        normalized = _normalize_name_entry(name, "zapier_ai_list")
        if normalized:
            incoming.append(normalized)

    allowed_sources = {"manual_seed", "zapier_ai_list"} | set(RSS_SOURCES.keys())
    existing = _filter_existing_products(current.get("products", []), allowed_sources)
    products = _merge_products(existing, incoming)
    payload = {
        "generated_at": _now_iso(),
        "source": "zapier_ai_list",
        "sources": ["manual_seed", "zapier_ai_list"] + list(RSS_SOURCES.keys()),
        "products": products
    }
    save_ai_products(payload)
    return payload


def sync_ai_products_sources() -> dict:
    current = load_ai_products()
    sources = load_ai_sources()
    incoming = []
    for source in sources:
        url = source.get("url")
        name = source.get("name") or url or "source"
        if not url:
            continue
        try:
            response = requests.get(url, timeout=12)
            if response.status_code != 200:
                continue
            html = response.text
        except Exception:
            continue

        if "toolify.ai" in url:
            names = _extract_tools_from_directory(html, "/tool/")
        elif "futurepedia.io" in url:
            names = _extract_tools_from_directory(html, "/tool/")
        elif "theresanaiforthat.com" in url:
            names = _extract_tools_from_directory(html, "/tool/")
        else:
            names = _parse_generic_product_list(html)

        # fall back to zapier parser for that specific page
        if "zapier.com/blog/best-ai-productivity-tools" in url:
            names = _parse_zapier_ai_list(html) or names

        for product_name in names:
            normalized = _normalize_name_entry(product_name, name)
            if normalized:
                normalized["source_url"] = url
                incoming.append(normalized)

    allowed_sources = {"manual_seed"} | {s.get("name") or s.get("url") for s in sources} | set(RSS_SOURCES.keys())
    existing = _filter_existing_products(current.get("products", []), allowed_sources)
    products = _merge_products(existing, incoming)
    payload = {
        "generated_at": _now_iso(),
        "source": "multi_source_sync",
        "sources": ["manual_seed"] + [s.get("name") or s.get("url") for s in sources],
        "products": products
    }
    save_ai_products(payload)
    return payload


def maybe_refresh_ai_products(max_age_hours: int = 24) -> dict:
    data = load_ai_products()
    ts = data.get("generated_at")
    if not ts:
        return sync_ai_products()
    try:
        last = datetime.fromisoformat(ts)
        if datetime.now(timezone.utc) - last > timedelta(hours=max_age_hours):
            return sync_ai_products()
    except Exception:
        return sync_ai_products()
    return data
