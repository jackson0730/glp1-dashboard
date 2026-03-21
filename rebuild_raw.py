#!/usr/bin/env python3
import sys, datetime
sys.path.insert(0, '/Users/xiaolongxiazhuanyongji/glp1-dashboard')
from crawl_glp1 import read_crawled_data, format_item, RAW_DATA_DIR

week_id = "2026-W11"
start_ts = datetime.datetime(2026, 3, 16).timestamp()
end_ts   = datetime.datetime(2026, 3, 22, 23, 59, 59).timestamp()

RAW_DATA_DIR.mkdir(exist_ok=True)
all_texts = []
for platform in ["xhs", "wb", "zhihu"]:
    for date_str in ["2026-03-20", "2026-03-21"]:
        items = read_crawled_data(platform, date_str)
        kept = 0
        for item in items:
            t = format_item(item, platform, start_ts, end_ts)
            if t:
                all_texts.append(t)
                kept += 1
        if kept:
            print(f"{platform} {date_str}: 保留 {kept} 条")

sep = "\n\n" + "─"*60 + "\n\n"
out = RAW_DATA_DIR / f"{week_id}.txt"
out.write_text(sep.join(all_texts), encoding="utf-8")
print(f"\n共 {len(all_texts)} 条，已写入 {out}")
