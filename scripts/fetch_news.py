#!/usr/bin/env python3
"""Fetch, score, cluster, and publish GLP-1 news for the static site."""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES_PATH = ROOT / "scripts" / "sources.yml"
DEFAULT_OUTPUT_PATH = ROOT / "data" / "news.json"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-pro"
GOOGLE_NEWS_DECODE_CACHE: dict[str, str] = {}
BEIJING_TZ = dt.timezone(dt.timedelta(hours=8))

SCORE_KEYS = ("relevance", "importance", "credibility", "freshness", "china_impact")

BASE_WEIGHTS = {
    "relevance": 0.25,
    "importance": 0.25,
    "credibility": 0.20,
    "freshness": 0.15,
    "china_impact": 0.15,
}

SOURCE_RULES = {
    "regulator": {"bonus": 12, "threshold": 58, "priority": 100},
    "company_official": {"bonus": 8, "threshold": 60, "priority": 90},
    "clinical_registry": {"bonus": 7, "threshold": 61, "priority": 85},
    "journal": {"bonus": 6, "threshold": 63, "priority": 80},
    "professional_media": {"bonus": 4, "threshold": 66, "priority": 70},
    "general_media": {"bonus": 0, "threshold": 72, "priority": 50},
    "social_kol": {"bonus": -12, "threshold": 82, "priority": 20},
}

CATEGORY_THRESHOLDS = {
    "regulatory_approval": 58,
    "clinical_trial": 62,
    "company": 60,
    "commercialization": 66,
    "safety": 66,
    "investment": 70,
    "research": 68,
}

CATEGORY_LABELS = {
    "regulatory_approval": "监管审批",
    "clinical_trial": "临床试验",
    "company": "药企动态",
    "commercialization": "商业化/医保",
    "safety": "安全性",
    "investment": "投融资",
    "research": "研究进展",
}

REGION_LABELS = {
    "china": "中国",
    "international": "国际",
}

GLP1_KEYWORDS = [
    "glp-1",
    "glp1",
    "glp 1",
    "司美格鲁肽",
    "semaglutide",
    "替尔泊肽",
    "tirzepatide",
    "玛仕度肽",
    "mazdutide",
    "利拉鲁肽",
    "liraglutide",
    "度拉糖肽",
    "dulaglutide",
    "依塞那肽",
    "exenatide",
    "orforglipron",
    "retatrutide",
    "cagrisema",
    "amycretin",
    "诺和盈",
    "wegovy",
    "ozempic",
    "mounjaro",
    "zepbound",
    "穆峰达",
    "信尔美",
    "减重针",
    "肥胖药",
]

DRUG_TERMS = {
    "司美格鲁肽": ["司美格鲁肽", "semaglutide", "ozempic", "wegovy", "诺和盈"],
    "替尔泊肽": ["替尔泊肽", "tirzepatide", "mounjaro", "zepbound", "穆峰达"],
    "玛仕度肽": ["玛仕度肽", "mazdutide", "信尔美"],
    "利拉鲁肽": ["利拉鲁肽", "liraglutide", "saxenda", "victoza"],
    "度拉糖肽": ["度拉糖肽", "dulaglutide", "trulicity"],
    "Retatrutide": ["retatrutide"],
    "Orforglipron": ["orforglipron"],
    "CagriSema": ["cagrisema"],
    "Amycretin": ["amycretin"],
}

COMPANY_TERMS = {
    "诺和诺德": ["诺和诺德", "novo nordisk"],
    "礼来": ["礼来", "eli lilly", "lilly"],
    "信达生物": ["信达", "信达生物", "innovent"],
    "甘李药业": ["甘李", "甘李药业", "ganlee"],
    "华东医药": ["华东医药", "huadong"],
    "博瑞医药": ["博瑞医药", "brightgene"],
    "翰森制药": ["翰森", "hansoh"],
    "恒瑞医药": ["恒瑞", "hengrui"],
    "辉瑞": ["辉瑞", "pfizer"],
    "勃林格殷格翰": ["勃林格", "boehringer"],
    "Structure": ["structure therapeutics"],
    "Roche": ["roche"],
}

WATCHED_WEIGHT_LOSS_COMPANIES = {
    company: COMPANY_TERMS[company]
    for company in ("辉瑞", "礼来", "诺和诺德", "信达生物")
}

WEIGHT_LOSS_CONTEXT_TERMS = [
    "减重",
    "减肥",
    "肥胖",
    "体重管理",
    "代谢",
    "weight loss",
    "obesity",
]

EVENT_TERMS = {
    "获批": ["获批", "批准", "上市", "approval", "approved", "nda", "bla"],
    "临床": ["临床", "iii期", "ii期", "phase 3", "phase iii", "phase 2", "trial"],
    "医保": ["医保", "支付", "报销", "商业化", "价格", "pricing"],
    "安全性": ["安全", "副作用", "不良反应", "胰腺炎", "停药", "safety"],
    "投融资": ["融资", "并购", "授权", "license", "acquisition", "deal"],
    "研究": ["论文", "研究", "机制", "数据", "study", "journal"],
    "网售限制": [
        "不得网售",
        "禁止网售",
        "网售限制",
        "网售禁令",
        "网络销售禁令",
        "禁止网络销售",
        "全网禁售",
        "网购新规",
        "纸质处方",
        "擦边球",
        "售卖漏洞",
        "自创适应症",
        "购药乱象",
        "规避监管",
    ],
}

STRONG_EVENT_TOKENS = {"获批", "临床", "医保", "安全性", "投融资", "研究", "网售限制"}
COMPANY_TOKENS = set(COMPANY_TERMS)
DRUG_TOKENS = set(DRUG_TERMS)
SPECIFIC_EVENT_TOKENS = {"网售限制"}

AUTHORITY_PATTERNS = [
    (("nmpa.gov.cn", "cde.org.cn", "fda.gov", "ema.europa.eu"), "regulator"),
    (
        (
            "novonordisk.com",
            "lilly.com",
            "innoventbio.com",
            "ganlee.com",
            "eastchinapharm.com",
            "hengrui.com",
            "hansoh.cn",
            "pfizer.com",
            "boehringer-ingelheim.com",
            "roche.com",
        ),
        "company_official",
    ),
    (("clinicaltrials.gov", "chictr.org.cn"), "clinical_registry"),
    (("nejm.org", "thelancet.com", "nature.com", "jamanetwork.com"), "journal"),
    (
        (
            "reuters.com",
            "fiercepharma.com",
            "endpts.com",
            "biospace.com",
            "pharmaphorum.com",
            "yaozh.com",
            "med.sina.com",
            "pharmcube.com",
            "vcbeat.top",
            "wuximediaglobal.com",
        ),
        "professional_media",
    ),
]


class ScoringError(RuntimeError):
    """Raised when model scoring cannot produce valid five-dimension scores."""


@dataclass
class Source:
    id: str
    name: str
    url: str
    region: str
    source_type: str
    category_hint: str
    enabled: bool = True


def clamp(value: float, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(round(value))))


def strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_datetime(value: str) -> str:
    if not value:
        return dt.datetime.now(dt.timezone.utc).isoformat()
    normalized_value = re.sub(r"\s+", " ", value.strip())
    try:
        parsed = email.utils.parsedate_to_datetime(normalized_value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc).isoformat()
    except (TypeError, ValueError):
        pass
    try:
        iso_value = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", normalized_value).replace(" ", "T", 1)
        parsed = dt.datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc).isoformat()
    except ValueError:
        return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize_iso_timezone(value: str) -> str:
    return re.sub(r"([+-]\d{2})$", r"\1:00", value.strip())


def parse_article_datetime(value: str) -> str:
    normalized = normalize_iso_timezone(html.unescape(value).strip()).replace(" ", "T", 1)
    if not re.search(r"(Z|[+-]\d{2}:\d{2})$", normalized):
        normalized = f"{normalized}+08:00"
    return parse_datetime(normalized)


def extract_article_published_at(html_text: str) -> str:
    patterns = [
        r"\['actime',\s*'([^']+)'\]",
        r"\['autime',\s*'([^']+)'\]",
        r'<meta[^>]+(?:property|name)=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+(?:property|name)=["\'](?:pubdate|publishdate|datePublished)["\'][^>]+content=["\']([^"\']+)["\']',
        r'"datePublished"\s*:\s*"([^"]+)"',
        r'"publishTime"\s*:\s*"([^"]+)"',
        r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.I)
        if match:
            return parse_article_datetime(match.group(1))
    return ""


def date_from_iso(value: str) -> dt.date:
    try:
        return parse_iso_datetime(value).date()
    except ValueError:
        return dt.datetime.now(dt.timezone.utc).date()


def parse_iso_datetime(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def beijing_yesterday_window(now: dt.datetime | None = None) -> tuple[dt.datetime, dt.datetime]:
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    yesterday = current.astimezone(BEIJING_TZ).date() - dt.timedelta(days=1)
    start = dt.datetime.combine(yesterday, dt.time(0, 0), tzinfo=BEIJING_TZ)
    end = start + dt.timedelta(days=1)
    return start.astimezone(dt.timezone.utc), end.astimezone(dt.timezone.utc)


def load_sources(path: Path = DEFAULT_SOURCES_PATH) -> list[Source]:
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise RuntimeError("sources.yml must be JSON-compatible or PyYAML must be installed") from exc
        data = yaml.safe_load(raw)
    sources = []
    for item in data.get("sources", []):
        sources.append(
            Source(
                id=item["id"],
                name=item["name"],
                url=item["url"],
                region=item.get("region", "international"),
                source_type=item.get("source_type", "general_media"),
                category_hint=item.get("category_hint", "company"),
                enabled=item.get("enabled", True),
            )
        )
    return [source for source in sources if source.enabled]


def fetch_text(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "GLP-1 News Bot/1.0 (+https://github.com/jackson0730)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def child_text(element: ET.Element, names: tuple[str, ...]) -> str:
    for child in list(element):
        local = child.tag.split("}")[-1].lower()
        if local in names:
            return "".join(child.itertext()).strip()
    return ""


def parse_feed(xml_text: str, source: Source) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    if root.tag.split("}")[-1].lower() == "feed":
        entries = [child for child in list(root) if child.tag.split("}")[-1].lower() == "entry"]
        return [normalize_atom_entry(entry, source) for entry in entries]
    channel = root.find("channel")
    if channel is None:
        channel = root
    items = [child for child in list(channel) if child.tag.split("}")[-1].lower() == "item"]
    return [normalize_rss_item(item, source) for item in items]


def normalize_rss_item(item: ET.Element, source: Source) -> dict[str, Any]:
    title = strip_html(child_text(item, ("title",)))
    summary = strip_html(child_text(item, ("description", "summary")))
    link = child_text(item, ("link", "guid"))
    published_at = parse_datetime(child_text(item, ("pubdate", "published", "updated", "date")))
    source_name = child_text(item, ("source",)) or source.name
    return make_item(title, summary, link, published_at, source, source_name)


def normalize_atom_entry(entry: ET.Element, source: Source) -> dict[str, Any]:
    title = strip_html(child_text(entry, ("title",)))
    summary = strip_html(child_text(entry, ("summary", "content")))
    link = ""
    for child in list(entry):
        if child.tag.split("}")[-1].lower() == "link":
            link = child.attrib.get("href", "")
            if link:
                break
    published_at = parse_datetime(child_text(entry, ("published", "updated")))
    return make_item(title, summary, link, published_at, source, source.name)


def make_item(
    title: str,
    summary: str,
    url: str,
    published_at: str,
    source: Source,
    source_name: str,
) -> dict[str, Any]:
    text = f"{title} {summary}"
    category = detect_category(text, source.category_hint)
    region = detect_region(text, source.region)
    source_type = classify_source_type(url, source_name, source.source_type)
    item_id = hashlib.sha256((url or f"{title}|{published_at}").encode("utf-8")).hexdigest()[:16]
    tags = sorted(extract_terms(text))
    return {
        "id": item_id,
        "title": title,
        "summary": summary,
        "url": url,
        "source": source_name,
        "source_id": source.id,
        "source_type": source_type,
        "source_priority": SOURCE_RULES[source_type]["priority"],
        "region": region,
        "region_label": REGION_LABELS.get(region, region),
        "category": category,
        "category_label": CATEGORY_LABELS.get(category, category),
        "tags": tags,
        "published_at": published_at,
    }


def resolve_google_news_url(url: str, decode: bool = False) -> str:
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    if "news.google.com" not in parsed.netloc:
        return url
    params = urllib.parse.parse_qs(parsed.query)
    for key in ("url", "q"):
        if params.get(key):
            return params[key][0]
    if decode:
        decoded = decode_google_news_url(url)
        if decoded:
            return decoded
    return url


def decode_google_news_url(url: str) -> str:
    if url in GOOGLE_NEWS_DECODE_CACHE:
        return GOOGLE_NEWS_DECODE_CACHE[url]
    parsed = urllib.parse.urlparse(url)
    article_id = parsed.path.rstrip("/").split("/")[-1]
    if not article_id:
        return ""
    try:
        try:
            html_text = fetch_text(f"https://news.google.com/articles/{article_id}", timeout=6)
        except (urllib.error.URLError, TimeoutError):
            html_text = fetch_text(f"https://news.google.com/rss/articles/{article_id}", timeout=6)
        signature = re.search(r'data-n-a-sg="([^"]+)"', html_text)
        timestamp = re.search(r'data-n-a-ts="([^"]+)"', html_text)
        if not signature or not timestamp:
            return ""
        inner = (
            '["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,'
            'null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],'
            f'"{article_id}",{timestamp.group(1)},"{signature.group(1)}"]'
        )
        payload = ["Fbv4je", inner]
        request = urllib.request.Request(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            data=f"f.req={urllib.parse.quote(json.dumps([[payload]]))}".encode("utf-8"),
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "User-Agent": "Mozilla/5.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=6) as response:
            text = response.read().decode("utf-8", errors="replace")
        parts = text.split("\n\n")
        if len(parts) < 2:
            return ""
        decoded_rows = json.loads(parts[1])[:-2]
        decoded_payload = json.loads(decoded_rows[0][2])
        decoded_url = decoded_payload[1]
        if isinstance(decoded_url, str) and decoded_url.startswith("http"):
            GOOGLE_NEWS_DECODE_CACHE[url] = decoded_url
            return decoded_url
    except (IndexError, KeyError, TypeError, ValueError, urllib.error.URLError, TimeoutError):
        return ""
    return ""


def enrich_published_at_from_article(item: dict[str, Any]) -> dict[str, Any]:
    if not item.get("source_id", "").startswith("google-"):
        return item
    url = item.get("url", "")
    if not url or "news.google.com" in urllib.parse.urlparse(url).netloc:
        return item
    try:
        article_time = extract_article_published_at(fetch_text(url, timeout=8))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return item
    if article_time:
        item["feed_published_at"] = item["published_at"]
        item["published_at"] = article_time
    return item


def is_glp1_related(item: dict[str, Any]) -> bool:
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    return any(keyword.lower() in text for keyword in GLP1_KEYWORDS) or has_company_weight_loss_context(text)


def detect_category(text: str, fallback: str = "company") -> str:
    lower = text.lower()
    checks = [
        ("regulatory_approval", ["获批", "批准", "上市申请", "受理", "nmpa", "cde", "fda", "ema", "approval"]),
        ("clinical_trial", ["临床", "iii期", "ii期", "phase 3", "phase iii", "phase 2", "trial"]),
        ("commercialization", ["医保", "报销", "定价", "价格", "销售额", "商业化", "supply", "shortage"]),
        ("safety", ["安全", "副作用", "不良反应", "胰腺炎", "停药", "safety", "adverse"]),
        ("investment", ["融资", "并购", "授权", "license", "acquisition", "deal", "ipo"]),
        ("research", ["论文", "研究", "机制", "数据", "journal", "study", "published"]),
    ]
    for category, keywords in checks:
        if any(keyword in lower for keyword in keywords):
            return category
    return fallback if fallback in CATEGORY_LABELS else "company"


def detect_region(text: str, fallback: str = "international") -> str:
    lower = text.lower()
    china_terms = ["中国", "国内", "nmpa", "cde", "医保", "华东", "信达", "恒瑞", "甘李", "翰森", "博瑞"]
    if any(term in lower for term in china_terms):
        return "china"
    return fallback if fallback in REGION_LABELS else "international"


def classify_source_type(url: str, source_name: str, fallback: str) -> str:
    haystack = f"{url} {source_name}".lower()
    for patterns, source_type in AUTHORITY_PATTERNS:
        if any(pattern in haystack for pattern in patterns):
            return source_type
    if "x.com" in haystack or "twitter.com" in haystack or "微博" in haystack:
        return "social_kol"
    return fallback if fallback in SOURCE_RULES else "general_media"


def extract_terms(text: str) -> set[str]:
    lower = text.lower()
    terms: set[str] = set()
    for canonical, aliases in {**DRUG_TERMS, **COMPANY_TERMS, **EVENT_TERMS}.items():
        if any(alias.lower() in lower for alias in aliases):
            terms.add(canonical)
    return terms


def has_company_weight_loss_context(text: str) -> bool:
    lower = text.lower()
    has_company = any(
        alias.lower() in lower
        for aliases in WATCHED_WEIGHT_LOSS_COMPANIES.values()
        for alias in aliases
    )
    has_weight_context = any(term.lower() in lower for term in WEIGHT_LOSS_CONTEXT_TERMS)
    return has_company and has_weight_context


def relevance_score_for_item(item: dict[str, Any]) -> int:
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    terms = extract_terms(text)
    has_glp1_keyword = any(keyword.lower() in text for keyword in GLP1_KEYWORDS)
    has_company_weight_loss = has_company_weight_loss_context(text)
    drug_terms = terms & DRUG_TOKENS
    company_terms = terms & COMPANY_TOKENS
    event_terms = terms & STRONG_EVENT_TOKENS

    if drug_terms and (company_terms or event_terms):
        return 88
    if has_glp1_keyword and company_terms and event_terms:
        return 84
    if drug_terms:
        return 74
    if has_glp1_keyword and (company_terms or event_terms):
        return 70
    if has_company_weight_loss and any(word in text for word in ["减重药", "减肥药", "肥胖药", "obesity drug", "weight loss drug"]):
        return 62
    if has_company_weight_loss:
        return 55
    if has_glp1_keyword:
        return 55
    if company_terms and any(word in text for word in ["减重", "肥胖", "糖尿病", "代谢"]):
        return 38
    return 15


def heuristic_scores(item: dict[str, Any]) -> dict[str, int]:
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    source_type = item.get("source_type", "general_media")
    recency_days = max((dt.datetime.now(dt.timezone.utc).date() - date_from_iso(item["published_at"])).days, 0)
    scores = {
        "relevance": relevance_score_for_item(item),
        "importance": 55,
        "credibility": 55 + SOURCE_RULES[source_type]["bonus"],
        "freshness": clamp(92 - recency_days * 7),
        "china_impact": 72 if item.get("region") == "china" else 38,
    }
    if any(word in text for word in ["获批", "批准", "phase 3", "iii期", "fda", "nmpa", "cde"]):
        scores["importance"] += 18
    if any(word in text for word in ["安全", "safety", "不良反应", "副作用"]):
        scores["importance"] += 12
    if any(word in text for word in ["中国", "国内", "医保", "nmpa", "cde"]):
        scores["china_impact"] += 12
    return {key: clamp(value) for key, value in scores.items()}


class DeepSeekScorer:
    def __init__(self, api_key: str | None, model: str = DEEPSEEK_MODEL, timeout: int = 20) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def score(self, item: dict[str, Any]) -> tuple[dict[str, int], str]:
        if not self.api_key:
            return heuristic_scores(item), "rules_fallback"
        last_error: Exception | None = None
        for _ in range(2):
            try:
                return self._call_model(item), self.model
            except Exception as exc:  # noqa: BLE001 - retry once and mark item if still invalid.
                last_error = exc
                time.sleep(1)
        raise ScoringError(str(last_error))

    def _call_model(self, item: dict[str, Any]) -> dict[str, int]:
        prompt = build_score_prompt(item)
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 512,
            "messages": [
                {
                    "role": "system",
                    "content": "你是 GLP-1 医药新闻编辑评分器。只输出 JSON，不输出解释。",
                },
                {"role": "user", "content": prompt},
            ],
        }
        request = urllib.request.Request(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        message = data["choices"][0]["message"]
        content = message.get("content") or message.get("reasoning_content") or ""
        return parse_score_json(content)


def build_score_prompt(item: dict[str, Any]) -> str:
    return f"""
请只根据下面这条 GLP-1 相关信息，给 5 个维度分别打 0-100 分。
不要计算最终分，不要判断是否精选，不要考虑来源权重。

维度定义：
- relevance：与 GLP-1 药物/肥胖/糖尿病治疗领域的相关性。
  * 0-20：几乎无关。只是泛健康、资本市场、公司新闻，未触及 GLP-1。
  * 21-40：弱相关。只顺带提到 GLP-1 或减重药，主体不是药物、临床、监管或商业化。
  * 41-60：中等相关。讨论 GLP-1 赛道或公司布局，但缺少具体药物、适应症、临床、审批或市场事件。
  * 61-80：高度相关。明确涉及 GLP-1 药物、适应症、临床数据、审批、商业化、价格、可及性或安全性。
  * 81-100：核心新闻。GLP-1 是事件主体，且包含明确药物、公司、监管、临床或商业结果。
- importance：对行业、临床、监管、商业格局的重要性。
- credibility：信息可信度与可验证性。
- freshness：新闻新鲜度和时效性。
- china_impact：对中国市场、监管、药企或患者可及性的影响。

只返回这个 JSON 结构：
{{"relevance":0,"importance":0,"credibility":0,"freshness":0,"china_impact":0}}

标题：{item.get("title", "")}
摘要：{item.get("summary", "")}
来源：{item.get("source", "")}
发布时间：{item.get("published_at", "")}
链接：{item.get("url", "")}
""".strip()


def parse_score_json(content: str) -> dict[str, int]:
    match = re.search(r"\{.*\}", content, flags=re.S)
    if not match:
        raise ScoringError("model response did not contain JSON")
    data = json.loads(match.group(0))
    scores: dict[str, int] = {}
    for key in SCORE_KEYS:
        if key not in data:
            raise ScoringError(f"missing score: {key}")
        scores[key] = clamp(float(data[key]))
    return scores


def compute_final_score(item: dict[str, Any], scores: dict[str, int]) -> int:
    base = sum(scores[key] * BASE_WEIGHTS[key] for key in SCORE_KEYS)
    source_type = item.get("source_type", "general_media")
    score = base + SOURCE_RULES[source_type]["bonus"]
    if item.get("region") == "china" and scores["china_impact"] >= 55:
        score += 5
    if item.get("category") in {"regulatory_approval", "clinical_trial", "safety"}:
        score += 3
    if scores["credibility"] < 45:
        score -= 10
    if scores["relevance"] < 50:
        score -= 20
    return clamp(score)


def is_selected(item: dict[str, Any], scores: dict[str, int], final_score: int, score_status: str) -> bool:
    if score_status == "needs_review":
        return False
    source_threshold = SOURCE_RULES[item.get("source_type", "general_media")]["threshold"]
    category_threshold = CATEGORY_THRESHOLDS.get(item.get("category", "company"), 68)
    threshold = max(source_threshold, category_threshold)
    return final_score >= threshold and scores["relevance"] >= 55 and scores["credibility"] >= 50


def verification_label(item: dict[str, Any], scores: dict[str, int], selected: bool, score_status: str) -> str:
    if score_status == "needs_review":
        return "待人工复核"
    if item.get("source_type") in {"regulator", "company_official", "clinical_registry", "journal"}:
        return "已确认"
    if scores["credibility"] < 50:
        return "低可信来源"
    if selected:
        return "待交叉验证"
    return "未入精选"


def score_one(item: dict[str, Any], scorer: DeepSeekScorer) -> dict[str, Any]:
    try:
        scores, scored_by = scorer.score(item)
        score_status = "ok"
    except ScoringError as exc:
        scores = {key: 0 for key in SCORE_KEYS}
        scored_by = scorer.model
        score_status = "needs_review"
        item["score_error"] = str(exc)
    final_score = compute_final_score(item, scores)
    selected = is_selected(item, scores, final_score, score_status)
    return {
        **item,
        "scores": scores,
        "scored_by": scored_by,
        "score_status": score_status,
        "quality_score": final_score,
        "selected": selected,
        "verification": verification_label(item, scores, selected, score_status),
    }


def add_scores(items: list[dict[str, Any]], scorer: DeepSeekScorer, workers: int = 1) -> list[dict[str, Any]]:
    total = len(items)
    if workers <= 1:
        scored = []
        for index, item in enumerate(items, start=1):
            print(f"scoring {index}/{total}: {item.get('title', '')[:80]}", file=sys.stderr)
            scored.append(score_one(item, scorer))
        return scored

    scored_by_index: dict[int, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for index, item in enumerate(items, start=1):
            print(f"queue scoring {index}/{total}: {item.get('title', '')[:80]}", file=sys.stderr)
            futures[executor.submit(score_one, item, scorer)] = index
        for future in concurrent.futures.as_completed(futures):
            index = futures[future]
            scored_by_index[index] = future.result()
            print(f"scored {len(scored_by_index)}/{total}", file=sys.stderr)
    return [scored_by_index[index] for index in range(1, total + 1)]


def cluster_tokens(item: dict[str, Any]) -> set[str]:
    text = f"{item.get('title', '')} {item.get('summary', '')}"
    tokens = extract_terms(text)
    if not tokens:
        tokens.add(re.sub(r"\W+", "", item.get("title", "").lower())[:20])
    return tokens


def related_item_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id", ""),
        "title": item["title"],
        "url": item["url"],
        "source": item["source"],
        "published_at": item["published_at"],
        "quality_score": item["quality_score"],
    }


def cluster_match_reason(tokens: set[str], existing: set[str]) -> str | None:
    shared = tokens & existing
    if not shared:
        return None
    if shared & SPECIFIC_EVENT_TOKENS:
        return "specific_event"

    shared_companies = shared & COMPANY_TOKENS
    shared_drugs = shared & DRUG_TOKENS
    shared_events = shared & STRONG_EVENT_TOKENS

    if shared_companies and (shared_events or shared_drugs):
        return "same_company"
    if shared_companies and len(shared) >= 2:
        return "same_company"
    if shared_companies and len(tokens | existing) <= 3:
        return "same_company"

    if shared_drugs and shared_events and len(shared) >= 3:
        return "same_drug_event"

    return None


def same_event(item: dict[str, Any], cluster: dict[str, Any]) -> bool:
    item_date = date_from_iso(item["published_at"])
    cluster_date = cluster["date"]
    if abs((item_date - cluster_date).days) > 3:
        return False
    tokens = cluster_tokens(item)
    existing = cluster["tokens"]
    return cluster_match_reason(tokens, existing) is not None


def cluster_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sorted_items = sorted(items, key=lambda item: item["published_at"], reverse=True)
    clusters: list[dict[str, Any]] = []
    for item in sorted_items:
        for cluster in clusters:
            if same_event(item, cluster):
                cluster["items"].append(item)
                cluster["tokens"].update(cluster_tokens(item))
                if date_from_iso(item["published_at"]) > cluster["date"]:
                    cluster["date"] = date_from_iso(item["published_at"])
                break
        else:
            clusters.append(
                {
                    "date": date_from_iso(item["published_at"]),
                    "tokens": cluster_tokens(item),
                    "items": [item],
                }
            )

    output = []
    for index, cluster in enumerate(clusters, start=1):
        cluster_id = f"event-{index:04d}"
        ranked = sorted(
            cluster["items"],
            key=lambda item: (
                item.get("source_priority", 0),
                item.get("quality_score", 0),
                item.get("published_at", ""),
            ),
            reverse=True,
        )
        primary = {**ranked[0]}
        related = ranked[1:]
        primary["cluster_id"] = cluster_id
        primary["is_primary"] = True
        primary["related_count"] = len(related)
        primary["related_items"] = [related_item_summary(item) for item in related]
        if related:
            primary["verification"] = "已聚类验证" if primary["selected"] else primary["verification"]
        output.append(primary)
    return sorted(output, key=lambda item: (item["selected"], item["quality_score"], item["published_at"]), reverse=True)


def item_fingerprint(item: dict[str, Any]) -> str:
    title = re.sub(r"\s+", " ", item.get("title", "").strip().lower())
    source = item.get("source", "").strip().lower()
    return f"{title}|{source}"


def collect_known_item_keys(events: list[dict[str, Any]]) -> tuple[set[str], set[str], set[str]]:
    ids: set[str] = set()
    urls: set[str] = set()
    fingerprints: set[str] = set()

    def add(item: dict[str, Any]) -> None:
        if item.get("id"):
            ids.add(item["id"])
        if item.get("url"):
            urls.add(item["url"])
        fingerprints.add(item_fingerprint(item))

    for event in events:
        add(event)
        for related in event.get("related_items", []):
            add(related)
    return ids, urls, fingerprints


def filter_new_items(items: list[dict[str, Any]], existing_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids, urls, fingerprints = collect_known_item_keys(existing_events)
    filtered = []
    for item in items:
        if item.get("id") in ids or item.get("url") in urls or item_fingerprint(item) in fingerprints:
            continue
        ids.add(item.get("id", ""))
        urls.add(item.get("url", ""))
        fingerprints.add(item_fingerprint(item))
        filtered.append(item)
    return filtered


def event_tokens(event: dict[str, Any]) -> set[str]:
    tokens = cluster_tokens(event)
    for related in event.get("related_items", []):
        tokens.update(cluster_tokens(related))
    return tokens


def event_date(event: dict[str, Any]) -> dt.date:
    dates = [date_from_iso(event["published_at"])]
    for related in event.get("related_items", []):
        if related.get("published_at"):
            dates.append(date_from_iso(related["published_at"]))
    return max(dates)


def item_matches_event(item: dict[str, Any], event: dict[str, Any]) -> bool:
    cluster = {"date": event_date(event), "tokens": event_tokens(event)}
    return same_event(item, cluster)


def item_rank(item: dict[str, Any]) -> tuple[int, int, str]:
    return (
        item.get("source_priority", 0),
        item.get("quality_score", 0),
        item.get("published_at", ""),
    )


def next_cluster_id(events: list[dict[str, Any]]) -> str:
    numbers = []
    for event in events:
        match = re.fullmatch(r"event-(\d+)", str(event.get("cluster_id", "")))
        if match:
            numbers.append(int(match.group(1)))
    return f"event-{(max(numbers) if numbers else 0) + 1:04d}"


def normalize_related_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    output = []
    for item in sorted(items, key=lambda entry: entry.get("published_at", ""), reverse=True):
        key = (item.get("id", ""), item.get("url", ""), item_fingerprint(item))
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def merge_item_into_event(event: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    related = list(event.get("related_items", []))
    if item_rank(item) > item_rank(event):
        merged = {**item}
        merged["cluster_id"] = event.get("cluster_id", "")
        merged["is_primary"] = True
        related = normalize_related_items([related_item_summary(event), *related])
        merged["related_items"] = related
        merged["related_count"] = len(related)
        if related:
            merged["verification"] = "已聚类验证" if merged.get("selected") else merged.get("verification", "")
        return merged

    merged = event
    related = normalize_related_items([*related, related_item_summary(item)])
    merged["related_items"] = related
    merged["related_count"] = len(related)
    if related:
        merged["verification"] = "已聚类验证" if merged.get("selected") else merged.get("verification", "")
    return merged


def merge_incremental_events(existing_events: list[dict[str, Any]], new_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = copy.deepcopy(existing_events)
    for event in events:
        event["related_items"] = normalize_related_items(event.get("related_items", []))
        event["related_count"] = len(event["related_items"])

    for item in sorted(new_items, key=lambda entry: entry.get("published_at", ""), reverse=True):
        for index, event in enumerate(events):
            if item_matches_event(item, event):
                events[index] = merge_item_into_event(event, item)
                break
        else:
            primary = {**item}
            primary["cluster_id"] = next_cluster_id(events)
            primary["is_primary"] = True
            primary["related_count"] = 0
            primary["related_items"] = []
            events.append(primary)

    return sorted(events, key=lambda item: (item["selected"], item["quality_score"], item["published_at"]), reverse=True)


def read_existing_events(output_path: Path) -> list[dict[str, Any]]:
    if not output_path.exists():
        return []
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    return payload.get("news", [])


def fetch_items(
    sources: list[Source],
    days: int,
    limit_per_source: int,
    since: dt.datetime | None = None,
    until: dt.datetime | None = None,
) -> list[dict[str, Any]]:
    cutoff = since or dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        try:
            parsed = parse_feed(fetch_text(source.url), source)
        except (ET.ParseError, urllib.error.URLError, TimeoutError) as exc:
            print(f"warning: failed to fetch {source.id}: {exc}", file=sys.stderr)
            continue
        for item in parsed[:limit_per_source]:
            if not item["title"] or not is_glp1_related(item):
                continue
            item["url"] = resolve_google_news_url(item["url"], decode=True)
            item = enrich_published_at_from_article(item)
            published = parse_iso_datetime(item["published_at"])
            if published < cutoff:
                continue
            if until is not None and published >= until:
                continue
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            items.append(item)
    return items


def build_payload(items: list[dict[str, Any]]) -> dict[str, Any]:
    selected_count = sum(1 for item in items if item["selected"])
    return {
        "site": "GLP-1 News",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "score_dimensions": list(SCORE_KEYS),
        "stats": {
            "events": len(items),
            "selected": selected_count,
            "related_reports": sum(item.get("related_count", 0) for item in items),
        },
        "news": items,
    }


def write_payload(payload: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and publish GLP-1 News data.")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--limit-per-source", type=int, default=30)
    parser.add_argument("--max-items", type=int, default=0, help="Limit items after fetch for smoke tests.")
    parser.add_argument("--incremental", action="store_true", help="Merge new scored items into the existing output.")
    parser.add_argument(
        "--window",
        choices=("rolling", "yesterday"),
        default="rolling",
        help="Fetch window. 'yesterday' means Beijing-time 00:00-24:00 yesterday.",
    )
    parser.add_argument("--model", default=DEEPSEEK_MODEL)
    parser.add_argument("--api-timeout", type=int, default=20)
    parser.add_argument("--score-workers", type=int, default=4)
    args = parser.parse_args()

    sources = load_sources(args.sources)
    since = until = None
    if args.window == "yesterday":
        since, until = beijing_yesterday_window()
        print(f"fetch window: {since.isoformat()} to {until.isoformat()} (Beijing yesterday)", file=sys.stderr)

    raw_items = fetch_items(sources, days=args.days, limit_per_source=args.limit_per_source, since=since, until=until)
    existing_events = read_existing_events(args.output) if args.incremental else []
    if args.incremental:
        before_count = len(raw_items)
        raw_items = filter_new_items(raw_items, existing_events)
        print(f"incremental mode: {before_count} fetched, {len(raw_items)} new after dedupe", file=sys.stderr)
    if args.max_items > 0:
        raw_items = raw_items[: args.max_items]
    if args.incremental and not raw_items:
        print(f"no new items; kept existing {args.output}")
        return 0
    scorer = DeepSeekScorer(os.getenv("DEEPSEEK_API_KEY"), model=args.model, timeout=args.api_timeout)
    scored_items = add_scores(raw_items, scorer, workers=max(1, args.score_workers))
    clustered = merge_incremental_events(existing_events, scored_items) if args.incremental else cluster_items(scored_items)
    write_payload(build_payload(clustered), args.output)
    print(f"wrote {args.output} with {len(clustered)} clustered events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
