import re

from langchain_core.messages import AIMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda, RunnableSequence

from worldweaver.llm_factory import create_llm
from worldweaver.models import NPCDialogueResponse, StoryNode
from worldweaver.prompt_loader import get_story_template, load_prompt

# Qwen3 등 thinking 모델이 출력하는 <think>...</think> 블록을 제거
_THINK_PATTERN = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def _strip_think_block(message: AIMessage) -> AIMessage:
    """LLM 응답에서 <think> 블록을 제거."""
    cleaned = _THINK_PATTERN.sub("", message.content).strip()
    return AIMessage(content=cleaned)


strip_think = RunnableLambda(_strip_think_block)


def build_story_chain() -> RunnableSequence:
    """LCEL 체인을 조립하여 반환. 프롬프트 템플릿은 JSON에서 로드."""
    tmpl = get_story_template()
    parser = JsonOutputParser(pydantic_object=StoryNode)

    prompt = PromptTemplate(
        template=tmpl["template"],
        input_variables=tmpl["input_variables"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )

    chain = (
        {
            "context": lambda x: x["retriever"].invoke(x["request"]),
            "request": lambda x: x["request"],
            "world_state": lambda x: x["world_state"],
            "recent_scenes": lambda x: x["recent_scenes"],
            "directives": lambda x: x["directives"],
            "state_change_schema": lambda x: x["state_change_schema"],
        }
        | prompt
        | create_llm()
        | strip_think
        | parser
    )

    return chain


def build_npc_dialogue_chain() -> RunnableSequence:
    """NPC 대화 전용 LCEL 체인을 조립하여 반환."""
    tmpl = load_prompt("npc_dialogue")
    parser = JsonOutputParser(pydantic_object=NPCDialogueResponse)

    prompt = PromptTemplate(
        template=tmpl["template"],
        input_variables=tmpl["input_variables"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )

    chain = (
        {
            "npc_context": lambda x: x["npc_context"],
            "world_state": lambda x: x["world_state"],
            "dialogue_history": lambda x: x["dialogue_history"],
            "player_input": lambda x: x["player_input"],
        }
        | prompt
        | create_llm()
        | strip_think
        | parser
    )

    return chain
