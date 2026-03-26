from typing import Any

from pydantic import BaseModel, Field


class Choice(BaseModel):
    text: str = Field(description="선택지 텍스트")
    edge_feature: str = Field(description="성향 (Aggressive, Diplomatic, Cautious)")
    next_node_prompt: str = Field(description="다음 씬 생성을 위한 프롬프트")
    choice_type: str = Field(
        default="story",
        description="선택지 타입: story(일반 진행), dialogue(NPC 대화), combat(전투 조우)",
    )
    enemy_name: str | None = Field(
        default=None,
        description="전투 대상 적 이름 (choice_type이 combat일 때)",
    )
    npc_name: str | None = Field(
        default=None,
        description="대화 대상 NPC 이름 (choice_type이 dialogue일 때)",
    )
    risky: bool = Field(
        default=False,
        description="이 선택지가 위험/도전적인지 여부. True이면 서사 판정이 적용된다",
    )


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


class EndingEpilogue(BaseModel):
    """엔딩 에필로그 LLM 응답 모델."""
    title: str = Field(description="엔딩 제목 (인상적인 한 줄)")
    epilogue: str = Field(description="에필로그 본문 (3-5 단락, 플레이 내용 반영)")
    final_line: str = Field(description="마지막 인상적인 한 줄 (여운을 남기는 문장)")
    tone: str = Field(description="에필로그의 전체 톤 (hopeful, tragic, bittersweet, triumphant 등)")


class NPCDialogueResponse(BaseModel):
    """NPC 대화 LLM 응답 모델."""
    response: str = Field(description="NPC의 대사 (1~3 단락)")
    disposition_delta: float = Field(
        default=0.0,
        description="호감도 변화량 (-0.2 ~ +0.2)",
    )
    action: str | None = Field(
        default=None,
        description="NPC 행동: give_quest, give_item, reveal_info, refuse, attack, 또는 null",
    )
    action_detail: str | None = Field(
        default=None,
        description="행동 상세 (퀘스트 내용, 아이템 이름, 비밀 정보 등)",
    )
    memory_note: str = Field(
        default="",
        description="NPC가 기억해야 할 이 대화의 요약",
    )
    should_end: bool = Field(
        default=False,
        description="대화가 자연스럽게 종료되어야 하는지",
    )
