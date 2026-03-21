#!/usr/bin/env python3
"""
GLP-1 舆情周报生成脚本

流程：Tavily搜索各品牌关键词 → 汇总原始数据 → Kimi分析总结 → 写入JSON

用法：
  python generate_report.py [week]
  week: 格式 YYYY-WNN（如 2026-W10）。不传则自动计算上一自然周。

环境变量：
  MOONSHOT_API_KEY   Kimi API key
  TAVILY_API_KEY     Tavily search API key
"""

import time
from openai import OpenAI
from tavily import TavilyClient
import json
import datetime
import os
import sys

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
RAW_DATA_DIR = os.path.join(os.path.dirname(__file__), "raw_data")

BRANDS = [
    {"name": "礼来", "product": "替尔泊肽", "trade_name": "穆峰达"},
    {"name": "信达", "product": "玛仕度肽", "trade_name": "信尔美"},
    {"name": "诺和诺德", "product": "司美格鲁肽", "trade_name": "诺和盈"},
    {"name": "辉瑞", "product": "埃诺格鲁肽", "trade_name": "先维盈"},
]

# 每个品牌的搜索关键词组合
SEARCH_QUERIES = [
    # 品牌专项
    "替尔泊肽 穆峰达 舆情 新闻",
    "玛仕度肽 信尔美 舆情 新闻",
    "司美格鲁肽 诺和盈 舆情 新闻",
    "埃诺格鲁肽 先维盈 辉瑞 GLP-1",
    # 行业通用
    "GLP-1 减重药 中国 新闻",
    "GLP-1 减肥针 微博 小红书 热搜",
    "GLP-1 NMPA 审批 适应症",
]


def get_last_week() -> tuple:
    today = datetime.date.today()
    this_monday = today - datetime.timedelta(days=today.weekday())
    last_monday = this_monday - datetime.timedelta(weeks=1)
    last_sunday = this_monday - datetime.timedelta(days=1)
    week_id = last_monday.strftime("%Y-W%W")
    return week_id, last_monday.strftime("%Y/%m/%d"), last_sunday.strftime("%Y/%m/%d")


def load_raw_data(week_id: str) -> str:
    """优先读取爬虫原始数据文件，没有则返回空"""
    raw_path = os.path.join(RAW_DATA_DIR, f"{week_id}.txt")
    if os.path.exists(raw_path):
        with open(raw_path, encoding="utf-8") as f:
            return f.read()
    return ""


def crawl_data(start: str, end: str) -> str:
    """用Tavily搜索各品牌关键词，返回汇总的原始文本"""
    tavily = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

    all_results = []
    for query in SEARCH_QUERIES:
        print(f"  搜索: {query}")
        try:
            resp = tavily.search(
                query=query,
                search_depth="advanced",
                max_results=5,
                include_answer=True,
            )
            # 收集搜索结果
            if resp.get("answer"):
                all_results.append(f"[搜索: {query}]\n摘要: {resp['answer']}")
            for r in resp.get("results", []):
                all_results.append(
                    f"[来源: {r.get('url', '')}]\n标题: {r.get('title', '')}\n内容: {r.get('content', '')[:500]}"
                )
        except Exception as e:
            print(f"  搜索失败 ({query}): {e}")

    return "\n\n---\n\n".join(all_results)


def build_prompt(week_id: str, start: str, end: str, raw_data: str) -> str:
    brand_list = "、".join(
        f"{b['name']}｜{b['product']}｜{b['trade_name']}" for b in BRANDS
    )
    # 截断原始数据，避免超出模型输入限制（保留前30000字符）
    if len(raw_data) > 30000:
        raw_data = raw_data[:30000] + "\n\n[原始数据过长，已截断]"
    return f"""你是一位医药行业资深舆情分析师。以下是从微博、小红书、知乎等平台爬取的关于GLP-1减重药物的真实用户内容，请基于这些数据生成专业舆情周报。

统计周期：{start} – {end}（北京时间）
周期ID：{week_id}
品牌范围：{brand_list}

=== 平台爬取原始数据 ===
{raw_data}
=== 原始数据结束 ===

分析要求：
1. 严格基于原始数据，不编造未出现的内容；若某品牌/平台数据不足，标注"本周期未检索到足够公开内容支持判断"
2. 原始数据每条格式为：[平台] #标签 / 标题 / 内容 / 发布时间 / 链接。请在 representative_posts 和 references 中保留原始链接
3. 标签含义：#推广/合作=品牌推广或电商合作内容；#副作用=用户反映不良反应；#疗效=减重效果讨论；#价格=费用/医保讨论；#审批/政策=监管动态
4. representative_posts 要尽量多选，覆盖各平台、各品牌、各标签类型，每个品牌至少选3条（如有）
5. 平台舆情观察要区分：自发讨论 vs 推广内容，正面体验 vs 副作用吐槽
6. 信息优先级：官方公告 > 权威媒体 > 医生/专业人士 > 普通用户UGC
7. 对于推广/合作内容，在 representative_posts 的 tags 中标注 "#推广/合作"，并在风险点中提示

请严格按照以下JSON格式输出，不要输出任何JSON以外的内容：

{{
  "week": "{week_id}",
  "period": "{start} – {end}",
  "generated_at": "",
  "executive_summary": ["结论1", "结论2", "结论3", "结论4", "结论5"],
  "industry_overview": "行业总览，基于搜索数据总结本周GLP-1赛道共性热点",
  "brands": [
    {{
      "company": "礼来",
      "product": "替尔泊肽",
      "trade_name": "穆峰达",
      "volume_level": "高/中/低",
      "volume_note": "声量来源说明",
      "events": [{{"text": "事件描述", "ref": "来源链接"}}],
      "platform_sentiment": {{
        "微博": {{"summary": "主要讨论主题", "focus": "用户关注点", "tone": "正面/中性/负面/争议"}},
        "小红书": {{"summary": "", "focus": "", "tone": ""}},
        "豆瓣": {{"summary": "", "focus": "", "tone": ""}},
        "知乎": {{"summary": "", "focus": "", "tone": ""}},
        "抖音/快手/bilibili": {{"summary": "", "focus": "", "tone": ""}}
      }},
      "keywords": ["关键词1", "关键词2"],
      "risks": ["风险1", "风险2"],
      "opportunities": ["机会1", "机会2"],
      "one_line": "一句话总结该品牌本周舆情状态"
    }},
    {{
      "company": "信达", "product": "玛仕度肽", "trade_name": "信尔美",
      "volume_level": "", "volume_note": "", "events": [],
      "platform_sentiment": {{"微博": {{"summary": "", "focus": "", "tone": ""}}, "小红书": {{"summary": "", "focus": "", "tone": ""}}, "豆瓣": {{"summary": "", "focus": "", "tone": ""}}, "知乎": {{"summary": "", "focus": "", "tone": ""}}, "抖音/快手/bilibili": {{"summary": "", "focus": "", "tone": ""}}}},
      "keywords": [], "risks": [], "opportunities": [], "one_line": ""
    }},
    {{
      "company": "诺和诺德", "product": "司美格鲁肽", "trade_name": "诺和盈",
      "volume_level": "", "volume_note": "", "events": [],
      "platform_sentiment": {{"微博": {{"summary": "", "focus": "", "tone": ""}}, "小红书": {{"summary": "", "focus": "", "tone": ""}}, "豆瓣": {{"summary": "", "focus": "", "tone": ""}}, "知乎": {{"summary": "", "focus": "", "tone": ""}}, "抖音/快手/bilibili": {{"summary": "", "focus": "", "tone": ""}}}},
      "keywords": [], "risks": [], "opportunities": [], "one_line": ""
    }},
    {{
      "company": "辉瑞", "product": "埃诺格鲁肽", "trade_name": "先维盈",
      "volume_level": "", "volume_note": "", "events": [],
      "platform_sentiment": {{"微博": {{"summary": "", "focus": "", "tone": ""}}, "小红书": {{"summary": "", "focus": "", "tone": ""}}, "豆瓣": {{"summary": "", "focus": "", "tone": ""}}, "知乎": {{"summary": "", "focus": "", "tone": ""}}, "抖音/快手/bilibili": {{"summary": "", "focus": "", "tone": ""}}}},
      "keywords": [], "risks": [], "opportunities": [], "one_line": ""
    }}
  ],
  "competitive_comparison": [
    {{"company": "礼来", "product": "替尔泊肽", "volume_level": "", "event_intensity": "强/中/弱", "sentiment": "正面为主/中性/负面为主/争议", "discussion_focus": "", "top_platform": "", "main_risk": "", "main_opportunity": ""}},
    {{"company": "信达", "product": "玛仕度肽", "volume_level": "", "event_intensity": "", "sentiment": "", "discussion_focus": "", "top_platform": "", "main_risk": "", "main_opportunity": ""}},
    {{"company": "诺和诺德", "product": "司美格鲁肽", "volume_level": "", "event_intensity": "", "sentiment": "", "discussion_focus": "", "top_platform": "", "main_risk": "", "main_opportunity": ""}},
    {{"company": "辉瑞", "product": "埃诺格鲁肽", "volume_level": "", "event_intensity": "", "sentiment": "", "discussion_focus": "", "top_platform": "", "main_risk": "", "main_opportunity": ""}}
  ],
  "representative_posts": [
    {{"brand": "品牌名", "platform": "平台", "tags": ["#推广/合作"], "summary": "内容摘要", "ref": "原文链接"}}
  ],
  "references": [
    {{"brand": "品牌名", "platform": "平台", "date": "日期", "title": "标题/话题", "type": "官方/媒体/UGC/热搜", "summary": "核心内容摘要", "url": "原文链接"}}
  ]
}}"""


def generate(week_id: str, start: str, end: str):
    print(f"\n=== 生成 {week_id} ({start} – {end}) 舆情报告 ===\n")

    # Step 1: 优先用爬虫数据，没有则用 Tavily
    raw_data = load_raw_data(week_id)
    if raw_data:
        print(f"【Step 1/2】使用爬虫原始数据（{len(raw_data)} 字符）\n")
    else:
        print("【Step 1/2】未找到爬虫数据，使用 Tavily 搜索...")
        raw_data = crawl_data(start, end)
        print(f"  共收集 {len(raw_data)} 字符的原始数据\n")

    # Step 2: Kimi 分析
    print("【Step 2/2】Kimi 分析总结中...")
    client = OpenAI(
        api_key=os.environ["MOONSHOT_API_KEY"],
        base_url="https://api.moonshot.cn/v1",
    )
    for attempt in range(1, 4):
        message = client.chat.completions.create(
            model="kimi-k2.5",
            max_tokens=16000,
            messages=[{"role": "user", "content": build_prompt(week_id, start, end, raw_data)}],
        )
        text = message.choices[0].message.content.strip()
        finish_reason = message.choices[0].finish_reason
        print(f"  第{attempt}次尝试：返回 {len(text)} 字符，finish_reason={finish_reason}")

        if finish_reason == "engine_overloaded":
            print(f"  服务器过载，等待30秒后重试...")
            time.sleep(30)
            continue

        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        if json_start != -1 and json_end > 0:
            try:
                report = json.loads(text[json_start:json_end])
                break
            except json.JSONDecodeError as e:
                print(f"  JSON解析失败: {e}，等待15秒后重试...")
                time.sleep(15)
                continue
    else:
        debug_path = os.path.join(DATA_DIR, f"{week_id}_raw_response.txt")
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(text)
        raise ValueError(f"3次尝试均失败，原始输出已保存至 {debug_path}")
    report["generated_at"] = datetime.datetime.now().isoformat()

    os.makedirs(DATA_DIR, exist_ok=True)
    out_path = os.path.join(DATA_DIR, f"{week_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n报告已保存：{out_path}")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) > 1:
        week_id = sys.argv[1]
        year, wnum = week_id.split("-W")
        monday = datetime.datetime.strptime(f"{year}-W{wnum}-1", "%Y-W%W-%w").date()
        sunday = monday + datetime.timedelta(days=6)
        start = monday.strftime("%Y/%m/%d")
        end = sunday.strftime("%Y/%m/%d")
    else:
        week_id, start, end = get_last_week()

    generate(week_id, start, end)
