import json
import unittest

from entry_on_kitchen import KitchenClient


class ThinkingOverrideTests(unittest.TestCase):
    def test_thinking_override_uses_canonical_top_level_key(self):
        client = KitchenClient(auth_code="test-auth-code")

        result = json.loads(
            client._prepare_body(
                {"message": "Solve this carefully"},
                llm_override="openai/gpt-5.4",
                thinking_override="HIGH",
            )
        )

        self.assertEqual(result["KITCHEN_THINKING_OVERRIDE"], "high")
        self.assertEqual(
            result["KITCHEN_MODELS_OVERRIDE"]["models__llm_override"],
            "openai/gpt-5.4",
        )

    def test_thinking_override_rejects_noncanonical_levels(self):
        client = KitchenClient(auth_code="test-auth-code")

        with self.assertRaises(ValueError):
            client._prepare_body({"message": "Hello!"}, thinking_override="auto")

    def test_existing_thinking_override_is_preserved_without_argument(self):
        client = KitchenClient(auth_code="test-auth-code")

        result = json.loads(
            client._prepare_body(
                {
                    "message": "Hello!",
                    "KITCHEN_THINKING_OVERRIDE": "medium",
                }
            )
        )

        self.assertEqual(result["KITCHEN_THINKING_OVERRIDE"], "medium")


if __name__ == "__main__":
    unittest.main()
