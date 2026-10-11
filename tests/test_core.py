from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from token_analyzer.core import (
    get_filter_options,
    get_matching_campaigns,
    get_token_ranking,
    import_workbook,
    normalize_term,
    query_campaign_drilldown,
    query_phrase,
    query_token_drilldown,
)


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
            orders DOUBLE,
            cost DOUBLE,
            sales DOUBLE
        )
        """
    )
    connection.executemany(
        "INSERT INTO search_records VALUES (?, ?, '', '', '', '', '', ?, ?, ?, 0, 0)",
        [
            (1, "white sandals women", 92, 4, 1),
            (2, "comfortable sandals women", 8, 2, 1),
            (3, "women leather sandals", 20, 5, 2),
            (4, "sandals womens", 10, 0, 0),
            (5, "凉鞋女", 30, 3, 1),
        ],
    )
    connection.execute("UPDATE search_records SET currency = 'USD', date_range = 'D1', portfolio = 'P1', campaign = 'A', ad_group = 'G1' WHERE record_id IN (1, 2)")
    connection.execute("UPDATE search_records SET currency = 'EUR', date_range = 'D2', portfolio = 'P2', campaign = 'B', ad_group = 'G2' WHERE record_id = 3")
    connection.execute("UPDATE search_records SET currency = 'USD', date_range = 'D1', portfolio = 'P3', campaign = 'A', ad_group = 'G3' WHERE record_id = 4")
    connection.execute("UPDATE search_records SET currency = 'CNY', date_range = 'D3', portfolio = 'P4', campaign = 'C', ad_group = 'G4' WHERE record_id = 5")
    connection.execute(
        """
        CREATE TABLE token_records AS
        SELECT DISTINCT records.record_id, parts.token
        FROM search_records AS records,
             unnest(string_split(records.search_term, ' ')) AS parts(token)
        WHERE parts.token <> ''
        """
    )
    connection.close()


class CoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "test.duckdb"
        build_database(self.database)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_normalize_term(self) -> None:
        self.assertEqual(normalize_term("  Sandals   WOMEN "), "sandals women")
        self.assertEqual(normalize_term("Ｂ０８ＡＢＣ１２３４"), "b08abc1234")

    def test_contiguous_phrase_and_metrics(self) -> None:
        result = query_phrase(self.database, "sandals women")

        self.assertEqual(result.frequency, 2)
        self.assertEqual(result.impressions, 100)
        self.assertEqual(result.clicks, 6)
        self.assertEqual(result.orders, 2)
        self.assertEqual(result.ctr, 0.06)
        self.assertAlmostEqual(result.cvr or 0, 1 / 3)
        self.assertEqual(
            {row["search_term"] for row in result.rows},
            {"white sandals women", "comfortable sandals women"},
        )

    def test_order_is_required(self) -> None:
        self.assertEqual(query_phrase(self.database, "women sandals").frequency, 0)

    def test_cjk_is_whole_term(self) -> None:
        self.assertEqual(query_phrase(self.database, "凉鞋女").frequency, 1)
        self.assertEqual(query_phrase(self.database, "凉鞋").frequency, 0)

    def test_search_results_follow_sort_dimension(self) -> None:
        by_clicks = query_phrase(self.database, "sandals", sort_by="clicks")
        by_conversion = query_phrase(self.database, "sandals", sort_by="cvr")

        self.assertEqual(by_clicks.rows[0]["search_term"], "women leather sandals")
        self.assertEqual(by_conversion.rows[0]["search_term"], "comfortable sandals women")

    def test_search_results_support_ranked_multi_field_sorting(self) -> None:
        connection = duckdb.connect(str(self.database))
        connection.executemany(
            "INSERT INTO search_records VALUES (?, ?, 'USD', 'D1', 'P1', 'A', 'G1', ?, ?, ?, 0, 0)",
            [
                (6, "alpha sandals", 50, 5, 1),
                (7, "beta sandals", 50, 10, 1),
            ],
        )
        connection.close()

        result = query_phrase(
            self.database,
            "sandals",
            sort_rules=(("impressions", "asc"), ("clicks", "desc")),
        )
        terms = [row["search_term"] for row in result.rows]

        self.assertLess(terms.index("beta sandals"), terms.index("alpha sandals"))
        with self.assertRaisesRegex(ValueError, "不能重复"):
            query_phrase(
                self.database,
                "sandals",
                sort_rules=(("clicks", "desc"), ("clicks", "asc")),
            )

    def test_token_ranking_defaults_to_clicks(self) -> None:
        result = get_token_ranking(self.database)

        self.assertEqual(result.rows[0]["search_term"], "sandals")
        self.assertEqual(result.rows[0]["clicks"], 11)
        self.assertEqual(result.rows[0]["frequency"], 4)
        self.assertEqual(result.total_items, 5)

    def test_token_ranking_can_sort_by_conversion(self) -> None:
        result = get_token_ranking(self.database, sort_by="cvr")

        self.assertEqual(result.rows[0]["search_term"], "comfortable")
        self.assertEqual(result.rows[0]["cvr"], 0.5)

    def test_all_results_can_be_loaded(self) -> None:
        ranking = get_token_ranking(self.database, limit=None)
        search = query_phrase(self.database, "sandals", limit=None)

        self.assertEqual(len(ranking.rows), ranking.total_items)
        self.assertEqual(len(search.rows), search.total_items)

    def test_filters_apply_to_ranking_search_and_options(self) -> None:
        ranking = get_token_ranking(self.database, filters={"currency": "EUR"})
        search = query_phrase(self.database, "sandals", filters={"currency": "USD"})
        options = get_filter_options(self.database)

        self.assertEqual(ranking.frequency, 1)
        self.assertEqual({row["search_term"] for row in ranking.rows}, {"leather", "sandals"})
        self.assertEqual(search.frequency, 3)
        self.assertEqual(search.clicks, 6)
        self.assertEqual(options["currency"], ["CNY", "EUR", "USD"])
        self.assertEqual(options["term_type"], ["关键词"])

    def test_filter_options_cascade_without_self_restriction(self) -> None:
        options = get_filter_options(self.database, filters={"currency": "EUR"})

        self.assertEqual(options["currency"], ["CNY", "EUR", "USD"])
        self.assertEqual(options["date_range"], ["D2"])
        self.assertEqual(options["portfolio"], ["P2"])
        self.assertEqual(options["campaign"], ["B"])
        self.assertEqual(options["ad_group"], ["G2"])

    def test_english_prepositions_are_excluded_from_token_ranking(self) -> None:
        connection = duckdb.connect(str(self.database))
        connection.execute(
            "INSERT INTO search_records VALUES (6, 'sandals for women on sale', 'USD', 'D1', 'P1', 'A', 'G1', 50, 7, 1, 0, 0)"
        )
        connection.execute(
            """
            INSERT INTO token_records
            SELECT 6, parts.token
            FROM unnest(string_split('sandals for women on sale', ' ')) AS parts(token)
            """
        )
        connection.close()

        ranking = get_token_ranking(self.database, limit=None)
        ranked_terms = {str(row["search_term"]) for row in ranking.rows}

        self.assertNotIn("for", ranked_terms)
        self.assertNotIn("on", ranked_terms)
        self.assertNotIn("women", ranked_terms)
        self.assertIn("sandals", ranked_terms)
        self.assertEqual(query_phrase(self.database, "for").frequency, 1)

    def test_gender_words_are_excluded_from_analysis_but_remain_searchable(self) -> None:
        connection = duckdb.connect(str(self.database))
        connection.execute(
            "INSERT INTO search_records VALUES (6, 'damen boots ladies', 'USD', 'D1', 'P1', 'A', 'G1', 50, 7, 1, 0, 0)"
        )
        connection.execute(
            "INSERT INTO token_records SELECT 6, parts.token FROM unnest(string_split('damen boots ladies', ' ')) AS parts(token)"
        )
        connection.close()

        ranked_terms = {str(row["search_term"]) for row in get_token_ranking(self.database, limit=None).rows}

        self.assertNotIn("women", ranked_terms)
        self.assertNotIn("womens", ranked_terms)
        self.assertNotIn("damen", ranked_terms)
        self.assertNotIn("ladies", ranked_terms)
        self.assertIn("boots", ranked_terms)
        self.assertEqual(query_phrase(self.database, "damen").frequency, 1)

    def test_table_filters_and_pagination_apply_to_all_results(self) -> None:
        first_page = get_token_ranking(self.database, limit=2, offset=0)
        second_page = get_token_ranking(self.database, limit=2, offset=2)
        filtered = get_token_ranking(self.database, row_filters={"clicks": {"min": 6}})
        term_filtered = get_token_ranking(self.database, row_filters={"search_term": {"contains": "lea"}})
        search_filtered = query_phrase(
            self.database,
            "sandals",
            row_filters={"clicks": {"min": 3}},
        )
        alphabetical = get_token_ranking(self.database, sort_by="search_term", ascending=True)

        self.assertFalse({row["search_term"] for row in first_page.rows} & {row["search_term"] for row in second_page.rows})
        self.assertEqual(filtered.total_items, 1)
        self.assertEqual(filtered.rows[0]["search_term"], "sandals")
        self.assertEqual([row["search_term"] for row in term_filtered.rows], ["leather"])
        self.assertEqual(search_filtered.total_items, 2)
        self.assertEqual(alphabetical.rows[0]["search_term"], "comfortable")

    def test_import_supports_csv_txt_and_xlsm_first_sheet(self) -> None:
        source = Path(self.temp_dir.name) / "report.csv"
        source.write_text(
            "Search Term,Impressions,Clicks,Orders,Ad Spend,Sales,Campaign\n"
            "red sandal,100,10,2,5,20,Campaign A\n",
            encoding="utf-8-sig",
        )
        imported = import_workbook(source, self.database)
        result = get_token_ranking(self.database, sort_by="cost")

        self.assertEqual(imported.imported_rows, 1)
        self.assertEqual(result.cost, 5.0)
        self.assertEqual(result.sales, 20.0)
        self.assertEqual(result.acos, 0.25)
        self.assertEqual(result.cpc, 0.5)
        self.assertEqual(result.rows[0]["cost"], 5.0)

        tab_source = Path(self.temp_dir.name) / "report.txt"
        tab_source.write_text("搜索词\t展示量\t点击量\t购买量\n凉鞋\t12\t3\t1\n", encoding="utf-8")
        import_workbook(tab_source, self.database)
        tab_result = query_phrase(self.database, "凉鞋")
        self.assertEqual(tab_result.frequency, 1)
        self.assertIsNone(tab_result.cost)
        self.assertIsNone(tab_result.rows[0]["sales"])

        workbook = Path(self.temp_dir.name) / "report.xlsx"
        with pd.ExcelWriter(workbook) as writer:
            pd.DataFrame({"搜索词": ["first sheet"], "展示量": [8], "点击量": [2], "购买量": [1]}).to_excel(
                writer,
                index=False,
                sheet_name="first",
            )
            pd.DataFrame({"not used": ["ignored"]}).to_excel(writer, index=False, sheet_name="second")
        macro_workbook = workbook.with_suffix(".xlsm")
        shutil.copyfile(workbook, macro_workbook)
        import_workbook(macro_workbook, self.database)
        self.assertEqual(query_phrase(self.database, "first sheet").frequency, 1)

    def test_gbk_semicolon_import_and_conflicting_headers_keep_old_database(self) -> None:
        source = Path(self.temp_dir.name) / "report.csv"
        source.write_text("搜索词;展示量;点击量;购买量\n凉鞋;12;3;1\n", encoding="gbk")
        import_workbook(source, self.database)
        self.assertEqual(query_phrase(self.database, "凉鞋").clicks, 3)

        conflict = Path(self.temp_dir.name) / "conflict.csv"
        conflict.write_text(
            "Search Term,Impressions,Clicks,Orders,Sales,7 Day Total Sales\nred sandal,1,1,1,2,3\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "字段映射冲突"):
            import_workbook(conflict, self.database)
        self.assertEqual(query_phrase(self.database, "凉鞋").frequency, 1)

    def test_cost_metrics_and_sort_direction(self) -> None:
        connection = duckdb.connect(str(self.database))
        connection.execute("UPDATE search_records SET cost = 10, sales = 20 WHERE record_id = 1")
        connection.execute("UPDATE search_records SET cost = 4, sales = 8 WHERE record_id = 2")
        connection.execute("UPDATE search_records SET cost = 2, sales = 4 WHERE record_id = 3")
        connection.execute("UPDATE search_records SET cost = 1, sales = 0 WHERE record_id = 4")
        connection.close()

        descending = query_phrase(self.database, "sandals", sort_by="cost")
        ascending = query_phrase(self.database, "sandals", sort_by="cost", ascending=True)
        zero_denominator = query_phrase(self.database, "womens")

        self.assertEqual(descending.rows[0]["search_term"], "white sandals women")
        self.assertEqual(ascending.rows[0]["search_term"], "sandals womens")
        self.assertEqual(descending.cost, 17.0)
        self.assertEqual(descending.sales, 32.0)
        self.assertAlmostEqual(descending.acos or 0, 17 / 32)
        self.assertIsNone(zero_denominator.rows[0]["acos"])
        self.assertIsNone(zero_denominator.rows[0]["cpc"])

    def test_token_drilldown_matches_the_exact_ranking_token(self) -> None:
        connection = duckdb.connect(str(self.database))
        connection.executemany(
            "INSERT INTO search_records VALUES (?, ?, 'EUR', 'D2', 'P2', ?, 'G2', ?, ?, ?, 0, 0)",
            [
                (6, "black rhinestone sandals", "Rhinestone", 60, 7, 1),
                (7, "white rhinestones sandals", "Rhinestones", 80, 11, 2),
            ],
        )
        connection.executemany(
            "INSERT INTO token_records VALUES (?, ?)",
            [(6, "black"), (6, "rhinestone"), (6, "sandals"), (7, "white"), (7, "rhinestones"), (7, "sandals")],
        )
        connection.close()

        ranking = get_token_ranking(self.database, filters={"currency": "EUR"}, limit=None)
        ranked = next(row for row in ranking.rows if row["search_term"] == "rhinestone")
        drilldown = query_token_drilldown(self.database, "rhinestone", filters={"currency": "EUR"})
        campaigns = get_matching_campaigns(self.database, "rhinestone", filters={"currency": "EUR"})

        self.assertEqual(drilldown.clicks, ranked["clicks"])
        self.assertEqual(drilldown.frequency, ranked["frequency"])
        self.assertEqual([row["search_term"] for row in drilldown.rows], ["black rhinestone sandals"])
        self.assertEqual(campaigns, ["Rhinestone"])

    def test_token_drilldown_treats_like_characters_as_literal_text(self) -> None:
        connection = duckdb.connect(str(self.database))
        connection.executemany(
            "INSERT INTO search_records VALUES (?, ?, 'USD', 'D1', 'P1', ?, 'G1', ?, ?, 0, 0, 0)",
            [
                (20, "save 50% sandals", "percent", 100, 7),
                (21, "save 50x sandals", "letter", 100, 13),
                (22, "model_a sandals", "underscore", 100, 5),
                (23, "modelxa sandals", "wildcard", 100, 11),
            ],
        )
        connection.executemany(
            "INSERT INTO token_records VALUES (?, ?)",
            [(20, "50%"), (21, "50x"), (22, "model_a"), (23, "modelxa")],
        )
        connection.close()

        percent = query_token_drilldown(self.database, "50%")
        underscore = query_token_drilldown(self.database, "model_a")

        self.assertEqual(percent.clicks, 7)
        self.assertEqual([row["search_term"] for row in percent.rows], ["save 50% sandals"])
        self.assertEqual(underscore.clicks, 5)
        self.assertEqual([row["search_term"] for row in underscore.rows], ["model_a sandals"])

    def test_import_hides_excluded_tokens_but_keeps_complete_search_terms(self) -> None:
        source = Path(self.temp_dir.name) / "excluded-words.csv"
        source.write_text(
            "搜索词,展示量,点击量,购买量\n"
            "sandals for women on sale,100,12,2\n",
            encoding="utf-8-sig",
        )

        import_workbook(source, self.database)
        ranking_terms = {str(row["search_term"]) for row in get_token_ranking(self.database, limit=None).rows}

        self.assertNotIn("for", ranking_terms)
        self.assertNotIn("on", ranking_terms)
        self.assertNotIn("women", ranking_terms)
        self.assertEqual(query_phrase(self.database, "for").rows[0]["search_term"], "sandals for women on sale")
        self.assertEqual(query_phrase(self.database, "women").clicks, 12)

    def test_campaign_drilldown_groups_exact_search_term_with_same_metrics(self) -> None:
        connection = duckdb.connect(str(self.database))
        connection.execute(
            "INSERT INTO search_records VALUES (6, 'white sandals women', 'USD', 'D1', 'P1', 'B', 'G2', 8, 6, 2, 3, 12)"
        )
        connection.close()

        result = query_campaign_drilldown(
            self.database,
            "white sandals women",
            sort_rules=[("clicks", "desc"), ("impressions", "asc")],
        )
        filtered = query_campaign_drilldown(
            self.database,
            "white sandals women",
            row_filters={"search_term": {"contains": "B"}},
        )

        self.assertEqual(result.total_items, 2)
        self.assertEqual([row["search_term"] for row in result.rows], ["B", "A"])
        self.assertEqual(result.frequency, 2)
        self.assertEqual(result.impressions, 100)
        self.assertEqual(result.clicks, 10)
        self.assertEqual(result.orders, 3)
        self.assertEqual(filtered.total_items, 1)
        self.assertEqual(filtered.rows[0]["search_term"], "B")


if __name__ == "__main__":
    unittest.main()
