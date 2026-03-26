from langchain_core.language_models import BaseChatModel

from worldweaver.prompt_loader import get_game_config

_PROVIDERS = {}


def _register_providers():
    """지원하는 LLM 제공자를 등록. 필요한 패키지가 없으면 건너뜀."""
    global _PROVIDERS

    try:
        from langchain_groq import ChatGroq
        _PROVIDERS["groq"] = ChatGroq
    except ImportError:
        pass

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _PROVIDERS["google"] = ChatGoogleGenerativeAI
    except ImportError:
        pass


def create_llm() -> BaseChatModel:
    """game_config.json의 provider 설정에 따라 LLM 인스턴스를 생성."""
    if not _PROVIDERS:
        _register_providers()

    cfg = get_game_config()["llm"]
    provider = cfg.get("provider", "groq")
    model = cfg["model"]

    if provider not in _PROVIDERS:
        available = ", ".join(_PROVIDERS.keys()) if _PROVIDERS else "없음"
        raise RuntimeError(
            f"LLM 제공자 '{provider}'를 사용할 수 없습니다. "
            f"해당 패키지가 설치되어 있는지 확인하세요. "
            f"사용 가능한 제공자: {available}"
        )

    llm_class = _PROVIDERS[provider]
    print(f"LLM 로드: {provider} / {model}")

    # Groq 제공자: max_tokens 명시 설정 (기본값이 낮아 JSON이 잘리는 문제 방지)
    extra_kwargs: dict = {}
    if provider == "groq":
        extra_kwargs["max_tokens"] = cfg.get("max_tokens", 8192)

    # Qwen3 모델의 thinking 모드 비활성화
    # thinking에 출력 토큰을 전부 소모하여 JSON을 출력하지 않는 문제 방지
    if "qwen" in model.lower():
        return llm_class(
            model=model,
            reasoning_format="hidden",
            **extra_kwargs,
        )

    return llm_class(model=model, **extra_kwargs)
