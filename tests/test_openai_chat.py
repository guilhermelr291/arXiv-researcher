"""Chat models post to the OpenAI Responses API."""

from __future__ import annotations

import unittest

from plan_based_researcher.agents import gate, planner, retrieve, search, summarizer, writer
from plan_based_researcher.eval import strategies
from plan_based_researcher.llm import openai_chat


class OpenAIChatTest(unittest.TestCase):
    def test_helper_sets_responses_api(self) -> None:
        model = openai_chat(model="gpt-5.6-luna", api_key="sk-test")
        self.assertTrue(model.use_responses_api)

    def test_explicit_false_is_kept(self) -> None:
        model = openai_chat(
            model="gpt-5.6-luna",
            api_key="sk-test",
            use_responses_api=False,
        )
        self.assertFalse(model.use_responses_api)

    def test_runners_share_the_helper(self) -> None:
        bound = (
            gate.ChatOpenAI,
            planner.ChatOpenAI,
            search.ChatOpenAI,
            retrieve.ChatOpenAI,
            writer.ChatOpenAI,
            summarizer.ChatOpenAI,
            strategies.ChatOpenAI,
        )
        for ctor in bound:
            self.assertIs(ctor, openai_chat)
