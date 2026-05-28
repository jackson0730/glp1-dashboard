import datetime as dt
import unittest

from scripts.fetch_news import (
    cluster_items,
    compute_final_score,
    is_selected,
    parse_score_json,
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
