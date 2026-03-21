#!/usr/bin/env python3
"""
Translate GLP-1 report JSON files from Chinese to English using Kimi API.
Saves translated file as <week>.en.json alongside the original.

Usage:
  python translate_json.py [week]          # e.g. 2026-W11
  python translate_json.py --all           # translate all weeks in data/

Env:
  MOONSHOT_API_KEY
"""
import json, os, sys, glob
from openai import OpenAI

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# Fields to skip translation (IDs, URLs, dates, numeric codes)
SKIP_KEYS = {"week", "period", "generated_at", "ref", "tone"}

SYSTEM_PROMPT = """You are a professional translator specializing in pharmaceutical and social media analytics.
Translate the following JSON values from Chinese to English.
Rules:
- Return ONLY valid JSON with identical structure and keys
- Translate all string values that are Chinese text
- Keep URLs, dates (YYYY-WNN, YYYY/MM/DD), numbers, and English words unchanged
- For volume_level: 高→High, 中→Medium, 低→Low
- For tone/sentiment: 正面→Positive, 负面→Negative, 中性→Neutral, 争议→Controversial, 正面为主→Mostly Positive, 负面为主→Mostly Negative, 正面/中性→Positive/Neutral, 负面/争议→Negative/Controversial
- For event_intensity: 强→Strong, 中→Medium, 弱→Weak
- Platform names: keep as pinyin/English (Weibo, Xiaohongshu, Zhihu, Douban, Douyin/Kuaishou/Bilibili)
- Brand/drug names: translate company names to English equivalents where standard (礼来→Eli Lilly, 诺和诺德→Novo Nordisk, 信达→Innovent, 辉瑞→Pfizer); keep drug names as-is or use INN
- Do not add explanations or markdown, return raw JSON only"""


def translate_chunk(client: OpenAI, data: dict) -> dict:
    payload = json.dumps(data, ensure_ascii=False)
    resp = client.chat.completions.create(
        model="kimi-k2.5",
        max_tokens=16000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Translate this JSON:\n{payload}"},
        ],
    )
    text = resp.choices[0].message.content.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)


def translate_file(week: str, client: OpenAI):
    src = os.path.join(DATA_DIR, f"{week}.json")
    dst = os.path.join(DATA_DIR, f"{week}.en.json")
    if not os.path.exists(src):
        print(f"  Not found: {src}")
        return
    if os.path.exists(dst):
        print(f"  Already exists: {dst} (skip)")
        return

    print(f"  Translating {week}...")
    d = json.load(open(src, encoding="utf-8"))

    # Translate in logical chunks to stay within token limits
    result = {}

    # Top-level scalar fields
    result["week"] = d["week"]
    result["period"] = d["period"]
    result["generated_at"] = d["generated_at"]

    # executive_summary (list of strings)
    chunk = {"executive_summary": d.get("executive_summary", [])}
    result["executive_summary"] = translate_chunk(client, chunk)["executive_summary"]

    # industry_overview (single string)
    chunk = {"industry_overview": d.get("industry_overview", "")}
    result["industry_overview"] = translate_chunk(client, chunk)["industry_overview"]

    # brands (translate one at a time)
    result["brands"] = []
    for b in d.get("brands", []):
        print(f"    brand: {b.get('company')}")
        result["brands"].append(translate_chunk(client, b))

    # competitive_comparison
    chunk = {"competitive_comparison": d.get("competitive_comparison", [])}
    result["competitive_comparison"] = translate_chunk(client, chunk)["competitive_comparison"]

    # representative_posts
    chunk = {"representative_posts": d.get("representative_posts", [])}
    result["representative_posts"] = translate_chunk(client, chunk)["representative_posts"]

    # references
    chunk = {"references": d.get("references", [])}
    result["references"] = translate_chunk(client, chunk)["references"]

    with open(dst, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  Saved: {dst}")


def main():
    api_key = os.environ.get("MOONSHOT_API_KEY")
    if not api_key:
        print("Error: MOONSHOT_API_KEY not set")
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url="https://api.moonshot.cn/v1")

    args = sys.argv[1:]
    if not args or args[0] == "--all":
        weeks = sorted(
            os.path.basename(f).replace(".json", "")
            for f in glob.glob(os.path.join(DATA_DIR, "????-W??.json"))
        )
    else:
        weeks = args

    for week in weeks:
        translate_file(week, client)


if __name__ == "__main__":
    main()
