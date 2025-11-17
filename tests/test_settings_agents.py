import os
import pytest

def test_agents_llm_mapping(monkeypatch):
    # Set env vars for an agent with a named llm
    monkeypatch.setenv("AGENTS__executor_agent__name", "executor_agent")
    monkeypatch.setenv("AGENTS__executor_agent__agent_type", "EXECUTOR")
    monkeypatch.setenv("AGENTS__executor_agent__llm__default__provider", "openai")
    monkeypatch.setenv("AGENTS__executor_agent__llm__default__model", "gpt-4")
    monkeypatch.setenv("AGENTS__executor_agent__llm__default__api_key", "sk-test-executor")

    # Reload settings to pick up env vars
    from src.model.setting import reload_settings

    settings = reload_settings()

    # Ensure agents mapping contains the configured agent
    agent_cfg = settings.get_agent_config("executor_agent")
    assert agent_cfg is not None, "executor_agent should be configured"
    assert agent_cfg.name == "executor_agent"
    assert agent_cfg.agent_type == "EXECUTOR"

    # Ensure the agent's llm mapping contains the named llm
    llm_cfg = agent_cfg.get_llm_config("default")
    assert llm_cfg is not None
    assert llm_cfg.model == "gpt-4"
    assert llm_cfg.provider == "openai"
    # SecretStr stored correctly
    assert llm_cfg.api_key.get_secret_value() == "sk-test-executor"


def test_multiple_agents_and_llms(monkeypatch):
    # Configure two agents and multiple llms
    monkeypatch.setenv("AGENTS__planner_agent__name", "planner_agent")
    monkeypatch.setenv("AGENTS__planner_agent__agent_type", "PLANNER")
    monkeypatch.setenv("AGENTS__planner_agent__llm__default__provider", "anthropic")
    monkeypatch.setenv("AGENTS__planner_agent__llm__default__model", "claude-v1")
    monkeypatch.setenv("AGENTS__planner_agent__llm__default__api_key", "sk-test-planner")

    # Also configure executor from previous test to ensure multiple agents coexist
    monkeypatch.setenv("AGENTS__executor_agent__name", "executor_agent")
    monkeypatch.setenv("AGENTS__executor_agent__agent_type", "EXECUTOR")
    monkeypatch.setenv("AGENTS__executor_agent__llm__secondary__provider", "openai")
    monkeypatch.setenv("AGENTS__executor_agent__llm__secondary__model", "gpt-4o")
    monkeypatch.setenv("AGENTS__executor_agent__llm__secondary__api_key", "sk-test-secondary")

    from src.model.setting import reload_settings

    settings = reload_settings()

    # planner checks
    planner = settings.get_agent_config("planner_agent")
    assert planner is not None
    assert planner.get_llm_config("default").model == "claude-v1"

    # executor checks
    executor = settings.get_agent_config("executor_agent")
    assert executor is not None
    assert executor.get_llm_config("secondary").model == "gpt-4o"

    # agents dict should contain both keys
    assert set(settings.agents.keys()) >= {"planner_agent", "executor_agent"}
