import random
import re

import networkx as nx


# ── NPC 세계관 이탈 반응 ──

NPC_DEFLECTION_RESPONSES = [
    "동료가 고개를 갸웃거리며 말합니다. \"...무슨 소리를 하는 거냐? 정신이 혼미한 건가? 지금 우리 앞에 적이 있다. 집중해라.\"",
    "수호자의 직감이 경고합니다. 지금 그런 생각에 빠져 있을 때가 아닙니다. 균열에서 뿜어져 나오는 왜곡의 기운이 점점 강해지고 있습니다.",
    "주변의 공기가 일순간 무거워집니다. 별자리의 빛이 깜빡이며, 마치 당신에게 본연의 임무를 상기시키는 듯합니다.",
    "고대의 목소리가 울려 퍼집니다. \"수호자여, 흐름의 법칙을 거스르는 말을 하지 마라. 세계의 균형이 흔들린다.\"",
    "동료가 당신의 어깨를 잡으며 말합니다. \"헛소리 집어치워. 지금 해야 할 일에 집중하자.\"",
]


def get_npc_deflection() -> dict:
    """세계관 이탈 시 NPC가 자연스럽게 무시하는 씬 데이터를 반환."""
    response_text = random.choice(NPC_DEFLECTION_RESPONSES)

    return {
        "title": "혼란의 순간",
        "description": response_text,
        "features": {"mood": "Mysterious", "morality_impact": "Neutral"},
        "choices": [],  # 빈 선택지 → game.py가 이전 선택지를 다시 제공
        "state_change": {},
    }


# ── 1단계: 입력 인젝션 패턴 필터 ──

# 프롬프트 인젝션에 사용되는 패턴들 (대소문자 무시)
INJECTION_PATTERNS = [
    r"#{2,}",                              # 마크다운 헤더 (## , ### )
    r"(?i)ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|rules?|prompts?)",
    r"(?i)disregard\s+(all\s+)?(previous|above|prior)",
    r"(?i)forget\s+(all\s+)?(previous|above|prior)",
    r"(?i)you\s+are\s+now\s+in\s+\w+\s+mode",
    r"(?i)system\s*(prompt|instruction|override|message)",
    r"(?i)output\s+(the|your|all)\s+(system|internal|hidden)",
    r"(?i)reveal\s+(your|the)\s+(instructions?|prompt|rules?)",
    r"(?i)jailbreak",
    r"(?i)DAN\s+mode",
    r"(?i)\bact\s+as\b.*\b(admin|root|developer|system)\b",
    r"\{.*format_instructions.*\}",        # 템플릿 변수 탈출 시도
    r"(?i)```\s*(system|assistant|user)",   # 역할 위장
]

_compiled_patterns = [re.compile(p) for p in INJECTION_PATTERNS]


def sanitize_input(text: str) -> str:
    """인젝션 패턴을 제거하고 정제된 텍스트를 반환.

    플레이어의 창의적 입력은 최대한 보존하면서,
    프롬프트 구조를 깨뜨리는 특수 패턴만 제거한다.
    """
    cleaned = text

    # 인젝션 패턴 매칭 → 해당 부분 제거
    for pattern in _compiled_patterns:
        cleaned = pattern.sub("", cleaned)

    # 연속된 공백/개행 정리
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()

    return cleaned


def detect_injection(text: str) -> list[str]:
    """인젝션 패턴이 있는지 탐지. 발견된 패턴 설명 목록을 반환."""
    found = []
    for pattern in _compiled_patterns:
        if pattern.search(text):
            found.append(pattern.pattern)
    return found


# ── 2단계: 지식 그래프 기반 주제 필터 (출력 검증) ──

class TopicFilter:
    """지식 그래프를 기반으로 LLM 출력이 세계관 범위 내인지 검증."""

    def __init__(self, knowledge_graph: nx.DiGraph | None = None):
        self._graph = knowledge_graph
        self._known_terms: set[str] = set()

        if self._graph:
            for node in self._graph.nodes:
                self._known_terms.add(node)
                desc = self._graph.nodes[node].get("description", "")
                if desc:
                    # 설명에서 핵심 명사 추출 (2글자 이상)
                    words = re.findall(r"[가-힣a-zA-Z]{2,}", desc)
                    self._known_terms.update(words)

    @property
    def is_available(self) -> bool:
        """지식 그래프가 로드되어 있는지."""
        return self._graph is not None and len(self._known_terms) > 0

    def check_input_relevance(self, text: str, threshold: float = 0.1) -> dict:
        """플레이어 입력이 세계관과 관련 있는지 검사.

        Returns:
            {"relevant": bool, "score": float}
        """
        if not self.is_available:
            return {"relevant": True, "score": 1.0}

        words = set(re.findall(r"[가-힣a-zA-Z]{2,}", text))
        if not words:
            return {"relevant": True, "score": 1.0}

        matched = words & self._known_terms
        score = len(matched) / len(words)
        return {"relevant": score >= threshold, "score": round(score, 3)}

    def check_scene_relevance(self, scene_data: dict, threshold: float = 0.15) -> dict:
        """생성된 씬이 세계관과 얼마나 관련 있는지 검사.

        Returns:
            {"relevant": bool, "score": float, "unknown_terms": list[str]}
        """
        if not self.is_available:
            return {"relevant": True, "score": 1.0, "unknown_terms": []}

        title = scene_data.get("title", "")
        description = scene_data.get("description", "")
        scene_text = f"{title} {description}"

        # 씬 텍스트에서 핵심 단어 추출 (2글자 이상)
        scene_words = set(re.findall(r"[가-힣a-zA-Z]{2,}", scene_text))

        if not scene_words:
            return {"relevant": True, "score": 1.0, "unknown_terms": []}

        # 지식 그래프 용어와의 교집합 비율
        matched = scene_words & self._known_terms
        score = len(matched) / len(scene_words)

        # 매칭되지 않은 주요 단어 (일반적인 한글 조사/부사 제외)
        common_words = {
            "그리고", "하지만", "그러나", "그래서", "때문에", "위해", "것이",
            "있는", "없는", "하는", "되는", "같은", "모든", "이미", "다시",
            "매우", "정말", "아직", "바로", "가장", "오직", "거의", "당신",
            "우리", "그들", "이것", "그것", "여기", "거기", "지금", "앞으로",
        }
        unknown = scene_words - self._known_terms - common_words

        return {
            "relevant": score >= threshold,
            "score": round(score, 3),
            "unknown_terms": sorted(unknown)[:10],  # 상위 10개만
        }


# ── 3단계: state_change 출력 검증 ──

# 게이지 변동량 허용 범위
MAX_GAUGE_DELTA = 0.3

def validate_state_change(state_change: dict, world_state) -> dict:
    """LLM이 출력한 state_change를 검증하고 비정상 값을 보정.

    Returns:
        보정된 state_change dict
    """
    validated = {}

    # 엔티티 상태 변경 — 이름에서 특수문자/인젝션 패턴 제거
    entities = state_change.get("entities_changed", {})
    if isinstance(entities, dict):
        clean_entities = {}
        for name, status in entities.items():
            clean_name = sanitize_input(str(name))[:50]  # 이름 길이 제한
            clean_status = sanitize_input(str(status))[:30]
            if clean_name and clean_status:
                clean_entities[clean_name] = clean_status
        validated["entities_changed"] = clean_entities

    # 게이지 변동 — 범위 제한
    gauge_deltas = state_change.get("gauge_deltas", {})
    if isinstance(gauge_deltas, dict):
        clean_deltas = {}
        for gauge_name, delta in gauge_deltas.items():
            if gauge_name in world_state.gauges:
                try:
                    delta_val = float(delta)
                    # 변동량을 허용 범위로 클램핑
                    clamped = max(-MAX_GAUGE_DELTA, min(MAX_GAUGE_DELTA, delta_val))
                    clean_deltas[gauge_name] = clamped
                except (ValueError, TypeError):
                    pass
        validated["gauge_deltas"] = clean_deltas

    # 속성 변경 — 값 sanitize
    props = state_change.get("properties_changed", {})
    if isinstance(props, dict):
        clean_props = {}
        for prop_name, value in props.items():
            if prop_name in world_state.properties:
                clean_props[prop_name] = sanitize_input(str(value))[:100]
        validated["properties_changed"] = clean_props

    # 컬렉션 추가/제거 — 아이템 이름 sanitize + 길이 제한
    for key in ("items_added", "items_removed"):
        col_data = state_change.get(key, {})
        if isinstance(col_data, dict):
            clean_col = {}
            for col_name, items in col_data.items():
                if col_name in world_state.collections and isinstance(items, list):
                    clean_items = [
                        sanitize_input(str(item))[:80]
                        for item in items[:10]  # 한 번에 최대 10개
                        if item
                    ]
                    clean_col[col_name] = clean_items
            validated[key] = clean_col

    return validated


# ── RAG 메모리 저장 전 sanitize ──

def sanitize_for_memory(text: str) -> str:
    """RAG 벡터 스토어에 저장하기 전에 텍스트를 정제."""
    cleaned = sanitize_input(text)
    # 길이 제한 (너무 긴 텍스트는 잘라냄)
    if len(cleaned) > 2000:
        cleaned = cleaned[:2000]
    return cleaned
