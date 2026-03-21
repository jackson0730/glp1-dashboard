#!/usr/bin/env python3
"""
GLP-1 平台爬取脚本

用法：
  python crawl_glp1.py [--platforms xhs wb zhihu] [--max-notes 20]

会在 MediaCrawler 目录下依次爬取各平台，
爬完后把所有 JSON 数据整理成原始文本，保存到 glp1-dashboard/raw_data/YYYY-WNN.txt

环境变量：无需额外设置，使用 MediaCrawler 自带的扫码登录
"""

import subprocess
import sys
import os
import json
import glob
import datetime
import argparse
from pathlib import Path

MEDIACRAWLER_DIR = Path(__file__).parent.parent / "BettaFish/MindSpider/DeepSentimentCrawling/MediaCrawler"
RAW_DATA_DIR = Path(__file__).parent / "raw_data"

# GLP-1 搜索关键词（精简为核心词，避免爬取时间过长）
GLP1_KEYWORDS = [
    "司美格鲁肽",
    "替尔泊肽",
    "玛仕度肽",
    "GLP-1减重",
]

# 平台名称映射
PLATFORM_NAMES = {
    "xhs": "小红书",
    "wb": "微博",
    "zhihu": "知乎",
    "bili": "bilibili",
    "dy": "抖音",
}

# 品牌关键词映射（用于打标签）
BRAND_KEYWORDS = {
    "礼来/替尔泊肽/穆峰达": ["替尔泊肽", "穆峰达", "礼来", "tirzepatide"],
    "信达/玛仕度肽/信尔美": ["玛仕度肽", "信尔美", "信达", "mazdutide"],
    "诺和诺德/司美格鲁肽/诺和盈": ["司美格鲁肽", "诺和盈", "诺和诺德", "semaglutide", "ozempic"],
    "辉瑞/埃诺格鲁肽/先维盈": ["埃诺格鲁肽", "先维盈", "辉瑞", "pfizer"],
}

CONTENT_TYPE_KEYWORDS = {
    "推广/合作": ["广告", "合作", "推广", "种草", "测评", "赠品", "福利", "优惠码", "代购", "团购"],
    "副作用": ["副作用", "恶心", "呕吐", "腹泻", "不良反应", "停药", "难受"],
    "疗效": ["瘦了", "减重", "效果", "有效", "疗效", "减了", "斤"],
    "价格": ["价格", "多少钱", "费用", "报销", "医保", "自费"],
    "审批/政策": ["获批", "审批", "NMPA", "适应症", "说明书", "上市"],
}


def detect_brand(text: str) -> str:
    text_lower = text.lower()
    for brand, kws in BRAND_KEYWORDS.items():
        if any(kw.lower() in text_lower for kw in kws):
            return brand
    return "通用GLP-1"


def detect_content_types(text: str) -> list:
    tags = []
    for tag, kws in CONTENT_TYPE_KEYWORDS.items():
        if any(kw in text for kw in kws):
            tags.append(tag)
    return tags


def set_mediacrawler_config(platform: str, keywords: list, max_notes: int):
    """直接修改 MediaCrawler base_config.py"""
    config_path = MEDIACRAWLER_DIR / "config" / "base_config.py"
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    keywords_str = ",".join(keywords)
    replacements = {
        'PLATFORM = ': f'PLATFORM = "{platform}"',
        'KEYWORDS = ': f'KEYWORDS = "{keywords_str}"',
        'CRAWLER_TYPE = ': f'CRAWLER_TYPE = "search"',
        'SAVE_DATA_OPTION = ': f'SAVE_DATA_OPTION = "json"',
        'CRAWLER_MAX_NOTES_COUNT = ': f'CRAWLER_MAX_NOTES_COUNT = {max_notes}',
        'ENABLE_GET_COMMENTS = ': f'ENABLE_GET_COMMENTS = True',
        'HEADLESS = ': f'HEADLESS = False',
    }

    lines = content.split("\n")
    new_lines = []
    skip_paren = False
    for line in lines:
        if skip_paren:
            if line.strip() == ")":
                skip_paren = False
            continue
        replaced = None
        for prefix, new_val in replacements.items():
            if line.startswith(prefix):
                replaced = new_val
                if line.rstrip().endswith("("):
                    skip_paren = True
                break
        new_lines.append(replaced if replaced is not None else line)

    with open(config_path, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines))


def run_mediacrawler(platform: str, keywords: list, max_notes: int):
    """运行 MediaCrawler 爬取"""
    print(f"\n{'='*50}")
    print(f"开始爬取: {PLATFORM_NAMES.get(platform, platform)}")
    print(f"{'='*50}")
    keywords_str = ",".join(keywords)
    result = subprocess.run(
        [
            sys.executable, "main.py",
            "--platform", platform,
            "--lt", "qrcode",
            "--crawler-type", "search",
            "--keywords", keywords_str,
            "--save-data-option", "json",
            "--get-comment", "True",
            "--headless", "False",
        ],
        cwd=MEDIACRAWLER_DIR,
    )
    return result.returncode == 0


# MediaCrawler 平台代码 → 实际数据目录名
PLATFORM_DIR = {
    "wb": "weibo",
    "xhs": "xhs",
    "zhihu": "zhihu",
    "bili": "bilibili",
    "dy": "douyin",
    "ks": "kuaishou",
    "tieba": "tieba",
}


def read_crawled_data(platform: str, date_str: str) -> list:
    """读取 MediaCrawler 输出的 JSON 文件，并按 URL 去重"""
    dir_name = PLATFORM_DIR.get(platform, platform)
    data_dir = MEDIACRAWLER_DIR / "data" / dir_name / "json"
    items = []
    seen_urls = set()

    for pattern in [f"search_contents_{date_str}.json", "search_contents_*.json"]:
        for fpath in glob.glob(str(data_dir / pattern)):
            try:
                with open(fpath, encoding="utf-8") as f:
                    data = json.load(f)
                for item in (data if isinstance(data, list) else [data]):
                    url = (item.get("note_url") or item.get("content_url") or
                           item.get("url") or item.get("video_url") or "")
                    key = url or str(item.get("note_id") or item.get("content_id") or id(item))
                    if key not in seen_urls:
                        seen_urls.add(key)
                        items.append(item)
            except Exception as e:
                print(f"  读取 {fpath} 失败: {e}")

    return items


GLP1_FILTER_WORDS = [
    "GLP", "glp", "司美格鲁肽", "替尔泊肽", "玛仕度肽", "埃诺格鲁肽",
    "诺和盈", "穆峰达", "信尔美", "先维盈", "减重", "减肥针", "降糖药",
    "肥胖", "体重", "注射", "利拉鲁肽", "度拉糖肽",
]


def is_glp1_related(text: str) -> bool:
    """过滤掉与GLP-1无关的噪音内容"""
    return any(w in text for w in GLP1_FILTER_WORDS)


def format_item(item: dict, platform: str, start_ts: float, end_ts: float):
    """把单条爬取结果格式化为文本，带标签；不在日期范围内或不相关返回 None"""
    # 知乎的 created_time 有时不准，优先用 updated_time，都没有则不过滤时间
    raw_ts = (item.get("time") or item.get("create_time") or
              item.get("updated_time") or item.get("created_time") or
              item.get("publish_time") or 0)
    if raw_ts:
        ts = raw_ts / 1000 if raw_ts > 1e10 else float(raw_ts)
        # 知乎时间戳有时偏差较大，放宽到前后4周
        if not (start_ts - 86400 * 28 <= ts <= end_ts + 86400 * 7):
            return None
        pub_time = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    else:
        pub_time = ""

    # 各平台字段名不同
    title = (item.get("title") or item.get("note_title") or item.get("video_title") or "")
    content = (item.get("content") or item.get("desc") or item.get("content_text") or
               item.get("note_content") or "")
    url = (item.get("note_url") or item.get("content_url") or item.get("url") or
           item.get("video_url") or "")
    author = (item.get("nickname") or item.get("user_nickname") or item.get("author_name") or "")
    likes = (item.get("liked_count") or item.get("like_count") or
             item.get("voteup_count") or "")  # 知乎用voteup_count

    full_text = f"{title} {content}"

    # 过滤无关噪音
    if not is_glp1_related(full_text):
        return None

    brand = detect_brand(full_text)
    content_tags = detect_content_types(full_text)
    platform_name = PLATFORM_NAMES.get(platform, platform)

    tags = [f"#{platform_name}", f"#{brand}"] + [f"#{t}" for t in content_tags]
    tags_str = " ".join(tags)

    lines = [
        f"[{platform_name}] {tags_str}",
        f"标题: {title}",
        f"内容: {content[:300]}{'...' if len(content) > 300 else ''}",
        f"作者: {author}  点赞: {likes}  发布时间: {pub_time}",
        f"链接: {url}",
    ]
    return "\n".join(lines)


def collect_raw_data(platforms: list, max_notes: int, week_id: str, start: str, end: str) -> str:
    """爬取所有平台，返回汇总文本"""
    # 计算时间戳范围
    start_ts = datetime.datetime.strptime(start, "%Y/%m/%d").timestamp()
    end_ts = datetime.datetime.strptime(end, "%Y/%m/%d").timestamp() + 86399  # 当天末尾

    today = datetime.date.today().strftime("%Y-%m-%d")
    all_texts = []
    total = skipped = 0

    for platform in platforms:
        set_mediacrawler_config(platform, GLP1_KEYWORDS, max_notes)
        success = run_mediacrawler(platform, GLP1_KEYWORDS, max_notes)

        if not success:
            print(f"  ⚠️  {platform} 爬取失败或被跳过")
            continue

        items = read_crawled_data(platform, today)
        kept = 0
        for item in items:
            text = format_item(item, platform, start_ts, end_ts)
            if text:
                all_texts.append(text)
                kept += 1
            else:
                skipped += 1
        total += kept
        print(f"  ✓ {PLATFORM_NAMES.get(platform, platform)}: {len(items)} 条 → 日期过滤后保留 {kept} 条")

    print(f"\n共保留 {total} 条（过滤掉 {skipped} 条不在 {start}–{end} 范围内的数据）")

    raw_text = f"\n\n{'─'*60}\n\n".join(all_texts)

    # 保存原始数据备份
    RAW_DATA_DIR.mkdir(exist_ok=True)
    raw_path = RAW_DATA_DIR / f"{week_id}.txt"
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(raw_text)
    print(f"原始数据已保存: {raw_path}")

    return raw_text


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--platforms", nargs="+", default=["xhs", "wb", "zhihu"],
                        help="平台列表，可选: xhs wb zhihu bili dy")
    parser.add_argument("--max-notes", type=int, default=20,
                        help="每个关键词最大爬取数量")
    parser.add_argument("--week", default=None,
                        help="周期ID，如 2026-W10，不传则自动计算上一自然周")
    args = parser.parse_args()

    if args.week:
        week_id = args.week
        year, wnum = week_id.split("-W")
        monday = datetime.datetime.strptime(f"{year}-W{wnum}-1", "%Y-W%W-%w").date()
        sunday = monday + datetime.timedelta(days=6)
        start = monday.strftime("%Y/%m/%d")
        end = sunday.strftime("%Y/%m/%d")
    else:
        today = datetime.date.today()
        this_monday = today - datetime.timedelta(days=today.weekday())
        last_monday = this_monday - datetime.timedelta(weeks=1)
        last_sunday = this_monday - datetime.timedelta(days=1)
        week_id = last_monday.strftime("%Y-W%W")
        start = last_monday.strftime("%Y/%m/%d")
        end = last_sunday.strftime("%Y/%m/%d")

    print(f"目标周期: {week_id}  ({start} – {end})")
    collect_raw_data(args.platforms, args.max_notes, week_id, start, end)
    print(f"\n完成！原始数据在 raw_data/{week_id}.txt")
    print(f"接下来运行: python3 generate_report.py {week_id}")
