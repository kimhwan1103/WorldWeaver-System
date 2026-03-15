from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableSequence

from worldweaver.llm_factory import create_llm
from worldweaver.models import NPCDialogueResponse, StoryNode
from worldweaver.prompt_loader import get_story_template, load_prompt


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
        | parser
    )

    return chain
