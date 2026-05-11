from pathlib import Path
import unittest

from harness_config import get_customer_context, load_harness_config


class HarnessConfigTests(unittest.TestCase):
    def test_load_sample_config(self) -> None:
        root = Path(__file__).resolve().parents[1]
        cfg = load_harness_config(root / "configs" / "customers.sample.json")
        self.assertGreaterEqual(len(cfg.customers), 2)
        self.assertEqual(cfg.default_customer_id, "acme_foods")

    def test_customer_context_resolves_paths(self) -> None:
        root = Path(__file__).resolve().parents[1]
        cfg = load_harness_config(root / "configs" / "customers.sample.json")
        ctx = get_customer_context(cfg, root, "nova_exports")
        self.assertTrue(str(ctx.db_path).endswith("customer_dbs/nova_exports.db"))
        self.assertTrue(str(ctx.dataset_root).endswith("raw_data/customers/nova_exports"))


if __name__ == "__main__":
    unittest.main()
