import random

DEFAULT_PERSONAS: dict[str, list[str]] = {
    "hero": ["Good", "Diplomatic", "Cautious"],
    "villain": ["Evil", "Aggressive"],
}


def choose_by_persona(
    choices: list[dict],
    persona: str = "hero",
    personas: dict[str, list[str]] | None = None,
) -> dict:
    """페르소나 성향에 맞는 선택지를 우선 선택하고, 없으면 랜덤 선택.

    personas dict가 전달되면 그것을 사용하고,
    없으면 기본 페르소나 설정을 사용한다.
    """
    if not personas:
        personas = DEFAULT_PERSONAS

    preferred_traits = personas.get(persona, [])
    preferred = [c for c in choices if c["edge_feature"] in preferred_traits]
    return random.choice(preferred) if preferred else random.choice(choices)
