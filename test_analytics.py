"""Unit tests verifying data cleaning, locale formatting, weakest outlets, and Telegram summary."""

import unittest
from pathlib import Path

from analytics import compute_dashboard, format_idr, load_and_clean_csv, load_csv_file, query_transactions

CSV_PATH = Path(__file__).resolve().parent / "sales.csv"


class TestSalesAnalytics(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows, cls.audit = load_csv_file(CSV_PATH)
        cls.dash_id = compute_dashboard(cls.rows, cls.audit, lang="id")
        cls.dash_en = compute_dashboard(cls.rows, cls.audit, lang="en")

    def test_data_cleaning_catches_all_traps(self) -> None:
        self.assertEqual(self.audit["raw_rows"], 1891)
        self.assertEqual(self.audit["duplicates_removed"], 3)
        self.assertEqual(self.audit["clean_rows"], 1888)
        self.assertEqual(self.audit["regions_normalized"], 10)
        self.assertEqual(self.audit["whitespace_trimmed"], 4)
        self.assertEqual(self.audit["blank_salesmen"], 5)
        self.assertEqual(self.audit["returns_kept"], 1)
        self.assertEqual(self.audit["returns_value_idr"], -528000)

    def test_indonesian_and_english_currency_formatting(self) -> None:
        self.assertEqual(format_idr(1_725_966_000, "id"), "Rp 1,73 M")
        self.assertEqual(format_idr(495_827_800, "id"), "Rp 495,8 jt")
        self.assertEqual(format_idr(564_000, "id"), "Rp 564 rb")
        self.assertEqual(format_idr(1_725_966_000, "en"), "Rp 1.73B")
        self.assertEqual(format_idr(495_827_800, "en"), "Rp 495.8M")

    def test_canonical_regions_and_brands(self) -> None:
        regions = {r["region"] for r in self.dash_id["by_region"]}
        self.assertEqual(
            regions,
            {"Jabodetabek", "Jawa Barat", "Jawa Tengah", "Jawa Timur", "Sumatera", "Kalimantan"},
        )
        self.assertEqual(len(self.dash_id["by_brand"]), 8)
        self.assertEqual(self.dash_id["by_region"][0]["region"], "Jabodetabek")
        self.assertEqual(self.dash_id["by_brand"][0]["brand"], "Kacang Dua Kelinci")

    def test_five_weakest_outlets_and_reasons(self) -> None:
        weakest_ids = [o["outlet_id"] for o in self.dash_id["weakest_outlets"]]
        self.assertEqual(
            weakest_ids,
            ["OUT1003", "OUT1026", "OUT1035", "OUT1045", "OUT1042"],
        )
        for outlet in self.dash_id["weakest_outlets"]:
            self.assertTrue(len(outlet["reasons"]) >= 1)

        drop_ids = [o["outlet_id"] for o in self.dash_id["sharpest_drops"]]
        self.assertEqual(drop_ids[0], "OUT1043")

    def test_telegram_summary_is_one_paragraph_and_locale_correct(self) -> None:
        id_text = self.dash_id["telegram_summary"]["text"]
        self.assertNotIn("\n", id_text)
        self.assertIn("Rp 1,73 M", id_text)
        self.assertIn("Rp 495,8 jt", id_text)
        self.assertIn("Toko Sinar Abadi", id_text)

        en_text = self.dash_en["telegram_summary"]["text"]
        self.assertNotIn("\n", en_text)
        self.assertIn("Rp 1.73B", en_text)
        self.assertIn("Jabodetabek", en_text)

        drops_dash = compute_dashboard(self.rows, self.audit, lang="id", outlet_mode="drops")
        self.assertIn("Minimarket Sido Muncul", drops_dash["telegram_summary"]["text"])
        self.assertIn("-68.7%", drops_dash["telegram_summary"]["text"])

    def test_dynamic_multi_month_dataset_comparison(self) -> None:
        sample_csv = "\n".join(
            [
                "date,invoice_no,region,branch,outlet_id,outlet_name,outlet_type,salesman,brand,sku,qty_carton,price_per_carton_idr,gross_sales_idr,discount_idr,net_sales_idr",
                "2027-01-10,INV1,Jabodetabek,Jakarta,OUT1,Toko A,Grosir,Andi,Sukro,Sukro 100g,10,100000,1000000,0,1000000",
                "2027-02-10,INV2,Jabodetabek,Jakarta,OUT1,Toko A,Grosir,Andi,Sukro,Sukro 100g,10,100000,1000000,0,1000000",
                "2027-03-10,INV3,Jabodetabek,Jakarta,OUT1,Toko A,Grosir,Andi,Sukro,Sukro 100g,15,100000,1500000,0,1500000",
            ]
        )
        rows, audit = load_and_clean_csv(sample_csv)
        dash = compute_dashboard(rows, audit, lang="id")
        self.assertEqual(dash["comparison"]["prev_month"], "2027-02")
        self.assertEqual(dash["comparison"]["curr_month"], "2027-03")
        self.assertEqual(dash["kpis"]["mom_pct"], 50.0)

    def test_transactions_search_sort_and_pagination(self) -> None:
        res = query_transactions(self.rows, search="RTR900001", page=1, page_size=10)
        self.assertEqual(res["total_rows"], 1)
        self.assertTrue(res["items"][0]["is_return"])

        paged = query_transactions(self.rows, sort_by="net_sales_idr", sort_dir="desc", page=1, page_size=20)
        self.assertEqual(len(paged["items"]), 20)
        self.assertGreaterEqual(paged["items"][0]["net_sales_idr"], paged["items"][1]["net_sales_idr"])


if __name__ == "__main__":
    unittest.main()
