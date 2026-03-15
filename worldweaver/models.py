from typing import Any

from pydantic import BaseModel, Field


class Choice(BaseModel):
    text: str = Field(description="선택지 텍스트")
    edge_feature: str = Field(description="성향 (Aggressive, Diplomatic, Cautious)")
    next_node_prompt: str = Field(description="다음 씬 생성을 위한 프롬프트")


class Features(BaseModel):
    mood: str = Field(description="씬의 분위기 (Tense, Mysterious, Hopeful 등)")
    morality_impact: str = Field(description="도덕적 영향 (Good, Evil, Neutral)")


class StoryNode(BaseModel):
    title: str = Field(description="씬 제목")
    description: str = Field(description="내러티브 본문 (2~3 단락)")
    features: Features = Field(description="씬 메타데이터")
    choices: list[Choice] = Field(description="플레이어 선택지 (2~5개)")
    state_change: dict[str, Any] = Field(
        default_factory=dict,
        description="이 씬에서 발생한 세계 상태 변화 (테마 스키마에 따라 동적 구조)",
    )
