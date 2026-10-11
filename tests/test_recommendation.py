from pathlib import Path
import sys
import tempfile
import unittest

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from token_analyzer.recommendation import get_recommendation_candidates


def build_database(path: Path) -> None:
    connection = duckdb.connect(str(path))
    connection.execute(
        """
        CREATE TABLE search_records(
            record_id BIGINT,
            search_term VARCHAR,
            currency VARCHAR,
            date_range VARCHAR,
            portfolio VARCHAR,
            campaign VARCHAR,
            ad_group VARCHAR,
            impressions DOUBLE,
            clicks DOUBLE,
            orders DOUBLE
        )
        """
    )
    connection.executemany(
        "INSERT INTO search_records VALUES (?, ?, ?, '', '', '', '', ?, ?, ?)",
        [
            (1, "trafficterm summer shoes", "USD", 1000, 500, 5),
            (2, "conversionterm winter boots", "EUR", 1000, 100, 60),
            (3, "tiny perfect sample", "USD", 10, 1, 1),
            (4, "white beach sandals", "USD", 200, 20, 4),
            (5, "black beach sandals", "EUR", 300, 15, 2),
        ],
    )
    connection.close()


class RecommendationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "test.duckdb"
        build_database(self.database)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_modes_change_priority(self) -> None:
        traffic = get_recommendation_candidates(self.database, mode="traffic")
        conversion = get_recommendation_candidates(self.database, mode="conversion")
        traffic_scores = {item.text: item.score for item in traffic.words}
        conversion_scores = {item.text: item.score for item in conversion.words}

        self.assertGreater(traffic_scores["trafficterm"], traffic_scores["conversionterm"])
        self.assertGreater(conversion_scores["conversionterm"], conversion_scores["trafficterm"])

    def test_search_scope_uses_all_matching_records(self) -> None:
        result = get_recommendation_candidates(self.database, scope_query="beach sandals")

        self.assertEqual(result.record_count, 2)
        self.assertEqual(result.scope_query, "beach sandals")
        self.assertIn("beach sandals", {item.text for item in result.phrases})
        self.assertNotIn("winter", {item.text for item in result.words})

    def test_phrase_candidates_are_contiguous(self) -> None:
        result = get_recommendation_candidates(self.database)
        phrases = {item.text for item in result.phrases}

        self.assertIn("white beach", phrases)
        self.assertIn("white beach sandals", phrases)
        self.assertNotIn("white sandals", phrases)

    def test_small_sample_conversion_is_smoothed(self) -> None:
        result = get_recommendation_candidates(self.database, mode="conversion")
        tiny = next(item for item in result.words if item.text == "tiny")

        self.assertEqual(tiny.cvr, 1.0)
        self.assertLess(tiny.smoothed_cvr, 1.0)

    def test_custom_weights_are_supported(self) -> None:
        result = get_recommendation_candidates(
            self.database,
            mode="custom",
            custom_weights={
                "orders": 1.0,
                "clicks": 0.0,
                "impressions": 0.0,
                "cvr": 0.0,
                "ctr": 0.0,
                "frequency": 0.0,
            },
        )

        scores = {item.text: item.score for item in result.words}
        self.assertGreater(scores["conversionterm"], scores["trafficterm"])

    def test_filters_limit_recommendation_scope(self) -> None:
        result = get_recommendation_candidates(self.database, filters={"currency": "EUR"})

        self.assertEqual(result.record_count, 2)
        self.assertEqual(result.filter_summary, "EUR")
        self.assertIn("winter", {item.text for item in result.words})
        self.assertNotIn("summer", {item.text for item in result.words})

    def test_english_prepositions_are_excluded_without_joining_neighbors(self) -> None:
        connection = duckdb.connect(str(self.database))
        connection.execute(
            "INSERT INTO search_records VALUES (6, 'sandals for women on sale', 'USD', '', '', '', '', 100, 10, 1)"
        )
        connection.close()

        result = get_recommendation_candidates(self.database)
        words = {item.text for item in result.words}
        phrases = {item.text for item in result.phrases}

        self.assertNotIn("for", words)
        self.assertNotIn("on", words)
        self.assertNotIn("women", words)
        self.assertFalse(any("for" in phrase.split() or "on" in phrase.split() for phrase in phrases))
        self.assertFalse(any("women" in phrase.split() for phrase in phrases))
        self.assertNotIn("sandals women", phrases)


if __name__ == "__main__":
    unittest.main()
