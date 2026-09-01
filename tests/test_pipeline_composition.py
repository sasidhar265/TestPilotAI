from app.agent_runtime import AgentRuntime
from app.agents import AgentRegistry
from app.config import Settings
from app.dependencies import get_multi_agent_pipeline
from app.generator import CopilotGenerator


def test_application_pipeline_wires_model_directed_agent_runtime(tmp_path) -> None:
    settings = Settings(
        organizational_memory_path=tmp_path / "memory.db",
        copilot_working_directory=tmp_path,
    )
    registry = AgentRegistry(CopilotGenerator(settings))

    pipeline = get_multi_agent_pipeline(registry, settings)

    assert isinstance(pipeline.runtime, AgentRuntime)
    assert pipeline.runtime.generator is pipeline.generator
    assert pipeline.runtime.validator is pipeline.validator
    assert pipeline.runtime.storage is pipeline.storage
