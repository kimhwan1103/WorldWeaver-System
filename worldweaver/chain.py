from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableSequence
from langchain_google_genai import ChatGoogleGenerativeAI

from worldweaver.config import LLM_MODEL
from worldweaver.models import StoryNode
from worldweaver.prompt_loader import get_story_template


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
        | ChatGoogleGenerativeAI(model=LLM_MODEL)
        | parser
    )

    return chain
