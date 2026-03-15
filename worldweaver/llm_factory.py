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
    return llm_class(model=model)
