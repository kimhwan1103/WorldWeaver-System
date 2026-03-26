import re

from langchain_core.messages import AIMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda, RunnableSequence

from worldweaver.llm_factory import create_llm
from worldweaver.models import EndingEpilogue, NPCDialogueResponse, StoryNode
from worldweaver.prompt_loader import get_game_config, get_story_template, load_prompt

# Qwen3 등 thinking 모델이 출력하는 <think>...</think> 블록을 제거
_THINK_PATTERN = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def _strip_think_block(message: AIMessage) -> AIMessage:
    """LLM 응답에서 <think> 블록을 제거."""
    content = message.content or ""
    # Gemini 등에서 content가 list[dict] 형태로 올 수 있음
    # 예: [{"type": "text", "text": "실제 내용"}]
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                parts.append(part["text"])
            else:
                parts.append(str(part))
        content = "\n".join(parts)
    elif not isinstance(content, str):
        content = str(content)
    # 닫힌 블록 제거
    content = _THINK_PATTERN.sub("", content)
    # 닫히지 않은 <think> 제거
    if "<think>" in content:
        idx = content.index("<think>")
        json_start = re.search(r"[{\[]", content[idx:])
        if json_start:
            content = content[:idx] + content[idx + json_start.start():]
        else:
            content = content[:idx]
    content = content.strip()
    # JSON 부분만 추출 (앞뒤 비-JSON 텍스트 제거)
    if content:
        match = re.search(r"(\{.*\}|\[.*\])", content, re.DOTALL)
        if match:
            content = match.group(1)
    # JSON 표준 위반 수정: +0.1 → 0.1 (값 위치의 양수 부호 제거)
    # 콜론 뒤, 쉼표 뒤, 대괄호 뒤 등 JSON 값 위치에서 + 부호 제거
    content = re.sub(r'(?<=[\s:,\[])(\+)(\d)', r'\2', content)
    return AIMessage(content=content)


strip_think = RunnableLambda(_strip_think_block)


def get_language_instruction(language: str = "") -> str:
    """언어 코드에 해당하는 출력 언어 지시문을 반환."""
    cfg = get_game_config()
    lang = language or cfg.get("default_language", "ko")
    supported = cfg.get("supported_languages", {})
    return supported.get(lang, supported.get("ko", "Write in Korean."))


def build_story_chain(language: str = "") -> RunnableSequence:
    """LCEL 스토리 생성 체인."""
    tmpl = get_story_template()
    parser = JsonOutputParser(pydantic_object=StoryNode)
    lang_instruction = get_language_instruction(language)

    prompt = PromptTemplate(
        template=tmpl["template"],
        input_variables=tmpl["input_variables"],
        partial_variables={
            "format_instructions": parser.get_format_instructions(),
            "language_instruction": lang_instruction,
        },
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


def build_npc_dialogue_chain(language: str = "") -> RunnableSequence:
    """LCEL NPC 대화 체인."""
    tmpl = load_prompt("npc_dialogue")
    parser = JsonOutputParser(pydantic_object=NPCDialogueResponse)
    lang_instruction = get_language_instruction(language)

    prompt = PromptTemplate(
        template=tmpl["template"],
        input_variables=tmpl["input_variables"],
        partial_variables={
            "format_instructions": parser.get_format_instructions(),
            "language_instruction": lang_instruction,
        },
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


def build_ending_chain(language: str = "") -> RunnableSequence:
    """LCEL 엔딩 에필로그 생성 체인."""
    tmpl = load_prompt("ending_template")
    parser = JsonOutputParser(pydantic_object=EndingEpilogue)
    lang_instruction = get_language_instruction(language)

    prompt = PromptTemplate(
        template=tmpl["template"],
        input_variables=tmpl["input_variables"],
        partial_variables={
            "format_instructions": parser.get_format_instructions(),
            "language_instruction": lang_instruction,
        },
    )

    chain = (
        {
            "ending_type": lambda x: x["ending_type"],
            "ending_hint": lambda x: x["ending_hint"],
            "play_summary": lambda x: x["play_summary"],
            "world_state": lambda x: x["world_state"],
            "npc_relationships": lambda x: x["npc_relationships"],
            "quest_summary": lambda x: x["quest_summary"],
        }
        | prompt
        | create_llm()
        | strip_think
        | parser
    )

    return chain
