"""Smoke tests for the agent harness configuration loader.

Verifies that ``configs/agents.json`` parses, that both shipped agents resolve,
and that the SO extraction agent can enumerate its customer datasets.
"""

from pathlib import Path
import unittest

from agents.config import load_config


class AgentsConfigTests(unittest.TestCase):
    def test_load_default_config(self) -> None:
        root = Path(__file__).resolve().parents[1]
        cfg = load_config(root / "configs" / "agents.json")
        self.assertIn("so_extraction", cfg.agent_ids())
        self.assertIn("product_retrieval", cfg.agent_ids())
        self.assertIn("so_then_retrieval", cfg.pipeline_ids())

    def test_so_extraction_datasets(self) -> None:
        cfg = load_config()
        agent = cfg.get_agent("so_extraction")
        dataset_ids = [d.id for d in agent.datasets()]
        self.assertIn("acme_foods", dataset_ids)
        self.assertIn("nova_exports", dataset_ids)
        self.assertGreater(len(agent.few_shot_pool()), 0)

    def test_pipeline_steps(self) -> None:
        cfg = load_config()
        pipeline = cfg.build_pipeline("so_then_retrieval")
        self.assertEqual([a.id for a in pipeline.agents], ["so_extraction", "product_retrieval"])


if __name__ == "__main__":
    unittest.main()
