import datetime as dt
from pathlib import Path
import unittest

from scripts.fetch_news import (
    CATEGORY_LABELS,
    CATEGORY_THRESHOLDS,
    SOURCE_RULES,
    cluster_items,
    compute_final_score,
    extract_article_published_at,
    is_glp1_related,
    is_selected,
    load_sources,
    parse_datetime,
    parse_score_json,
    relevance_score_for_item,
)


def item(source_type, category="company", title="GLP-1 news"):
    return {
        "id": f"{source_type}-{category}",
        "title": title,
        "summary": "GLP-1 司美格鲁肽 中国 获批",
        "url": "https://example.com",
        "source": source_type,
        "source_type": source_type,
        "source_priority": {"company_official": 90, "social_kol": 20, "professional_media": 70}.get(source_type, 50),
        "region": "china",
        "category": category,
        "published_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "quality_score": 60,
        "selected": True,
    }


class PipelineTest(unittest.TestCase):
    def test_parse_score_json_clamps_and_ignores_text(self):
        scores = parse_score_json('结果如下 {"relevance":101,"importance":60,"credibility":55,"freshness":50,"china_impact":-3}')
        self.assertEqual(scores["relevance"], 100)
        self.assertEqual(scores["china_impact"], 0)

    def test_extract_article_published_at_prefers_origin_time(self):
        html = """
        <script>
        _pb = [
          ['aid', '103116315'],
          ['actime', '2026-04-02T12:10:26+08'],
          ['autime', '2026-04-02T12:10:26+08']
        ];
        </script>
        """
        self.assertEqual(extract_article_published_at(html), "2026-04-02T04:10:26+00:00")

    def test_extract_article_published_at_treats_naive_time_as_beijing(self):
        html = "<em>2026-05-27 09:37:00</em>"
        self.assertEqual(extract_article_published_at(html), "2026-05-27T01:37:00+00:00")

    def test_parse_datetime_accepts_numeric_rss_timezone_with_extra_spaces(self):
        self.assertEqual(parse_datetime("2026-05-29 19:00:15  +0800"), "2026-05-29T11:00:15+00:00")

    def test_sources_config_uses_unique_valid_enabled_sources(self):
        sources = load_sources()
        ids = [source.id for source in sources]
        urls = [source.url for source in sources]
        expected_ids = {
            "huxiu-rss",
            "36kr-feed",
            "anyfeeder-infzm-news",
            "anyfeeder-cctvnewscenter",
            "anyfeeder-people-daily",
            "anyfeeder-newsxinhua",
            "anyfeeder-wowjiemian",
            "anyfeeder-cctvyscj",
            "anyfeeder-thepapernews",
            "anyfeeder-dxy",
        }

        self.assertTrue(expected_ids.issubset(set(ids)))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(urls), len(set(urls)))
        for source in sources:
            self.assertIn(source.source_type, SOURCE_RULES)
            self.assertIn(source.category_hint, CATEGORY_LABELS)

    def test_strict_glp1_filter_rejects_general_news(self):
        general_news = {"title": "铁路新规6月1日起实施", "summary": "拒绝补票旅客将被限制购票"}
        glp1_news = {"title": "GLP-1减肥药网售限制升级", "summary": "司美格鲁肽仍需处方"}

        self.assertFalse(is_glp1_related(general_news))
        self.assertTrue(is_glp1_related(glp1_news))

    def test_source_threshold_makes_same_score_selective(self):
        scores = {
            "relevance": 60,
            "importance": 60,
            "credibility": 60,
            "freshness": 60,
            "china_impact": 60,
        }
        official = item("company_official")
        social = item("social_kol")
        self.assertTrue(is_selected(official, scores, 60, "ok"))
        self.assertFalse(is_selected(social, scores, 60, "ok"))

    def test_final_score_uses_code_weighting(self):
        scores = {
            "relevance": 80,
            "importance": 80,
            "credibility": 80,
            "freshness": 80,
            "china_impact": 80,
        }
        official_score = compute_final_score(item("company_official"), scores)
        social_score = compute_final_score(item("social_kol"), scores)
        self.assertGreater(official_score, social_score)

    def test_heuristic_relevance_uses_rubric_bands(self):
        core = item("professional_media", "clinical_trial", "恒瑞口服小分子GLP-1 III期研究成功")
        core["summary"] = ""
        generic = item("professional_media", "company", "翰宇药业凭GLP-1赛道走出增长新曲线")
        generic["summary"] = ""
        unrelated = item("professional_media", "company", "某药企发布年度资本市场报告")
        unrelated["summary"] = ""

        self.assertGreaterEqual(relevance_score_for_item(core), 81)
        self.assertGreaterEqual(relevance_score_for_item(generic), 41)
        self.assertLessEqual(relevance_score_for_item(generic), 60)
        self.assertLessEqual(relevance_score_for_item(unrelated), 20)

    def test_scoring_page_lists_source_rules(self):
        html = Path("scoring.html").read_text(encoding="utf-8")
        for source_type, rule in SOURCE_RULES.items():
            self.assertIn(source_type, html)
            self.assertIn(f"<td>{rule['bonus']:+d}</td>", html)
            self.assertIn(f"<td>{rule['threshold']}</td>", html)
            self.assertIn(f"<td>{rule['priority']}</td>", html)

    def test_scoring_page_lists_category_thresholds(self):
        html = Path("scoring.html").read_text(encoding="utf-8")
        for category, threshold in CATEGORY_THRESHOLDS.items():
            self.assertIn(CATEGORY_LABELS[category], html)
            self.assertIn(f"<td>{category}</td>", html)
            self.assertIn(f"<td>{threshold}</td>", html)

    def test_cluster_keeps_authoritative_primary(self):
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        official = {
            **item("company_official", "regulatory_approval", "诺和诺德司美格鲁肽 中国 获批"),
            "id": "official",
            "published_at": now,
            "quality_score": 68,
        }
        media = {
            **item("professional_media", "regulatory_approval", "诺和诺德司美格鲁肽 减重适应症 获批"),
            "id": "media",
            "published_at": now,
            "quality_score": 88,
        }
        clustered = cluster_items([media, official])
        self.assertEqual(len(clustered), 1)
        self.assertEqual(clustered[0]["id"], "official")
        self.assertEqual(clustered[0]["related_count"], 1)

    def test_cluster_uses_strong_event_not_drug_only(self):
        now = dt.datetime(2026, 5, 18, tzinfo=dt.timezone.utc).isoformat()
        web_sale_a = {
            **item("professional_media", "commercialization", "司美格鲁肽按新规不得网售，但电商仍在打擦边球"),
            "id": "web-sale-a",
            "summary": "",
            "published_at": now,
        }
        web_sale_b = {
            **item("professional_media", "commercialization", "警惕减重针乱象，新规禁止网售但线上仍存售卖漏洞"),
            "id": "web-sale-b",
            "summary": "",
            "published_at": now,
        }
        web_sale_c = {
            **item("professional_media", "commercialization", "电商平台用高血糖标签规避GLP-1减肥药网售禁令"),
            "id": "web-sale-c",
            "summary": "",
            "published_at": now,
        }
        oral_tablet = {
            **item("professional_media", "company", "诺和诺德将海外推出司美格鲁肽口服片"),
            "id": "oral-tablet",
            "summary": "",
            "published_at": now,
        }
        clustered = cluster_items([web_sale_a, web_sale_b, web_sale_c, oral_tablet])
        cluster_ids = {entry["id"]: entry["related_count"] for entry in clustered}
        self.assertEqual(len(clustered), 2)
        self.assertIn(2, cluster_ids.values())

    def test_cluster_does_not_merge_generic_clinical_news(self):
        now = dt.datetime(2026, 5, 27, tzinfo=dt.timezone.utc).isoformat()
        hengrui = {
            **item("professional_media", "clinical_trial", "恒瑞口服小分子GLP-1 III期研究成功"),
            "id": "hengrui",
            "summary": "",
            "published_at": now,
        }
        lilly = {
            **item("professional_media", "clinical_trial", "礼来口服GLP-1药物III期数据亮眼"),
            "id": "lilly",
            "summary": "",
            "published_at": now,
        }
        clustered = cluster_items([hengrui, lilly])
        self.assertEqual(len(clustered), 2)


if __name__ == "__main__":
    unittest.main()
