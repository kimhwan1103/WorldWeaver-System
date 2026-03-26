import json
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_THEMES_DIR = _PROMPTS_DIR / "themes"

_cache: dict[str, dict] = {}


def load_prompt(name: str) -> dict:
    """prompts/ 디렉토리에서 JSON 파일을 로드하고 캐싱.

    sections 구조가 있고 template이 없으면 자동으로 template을 조립한다.
    """
    if name in _cache:
        return _cache[name]

    file_path = _PROMPTS_DIR / f"{name}.json"
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    if "template" not in data and "sections" in data:
        data["template"] = _assemble_template(data)

    _cache[name] = data
    return data


def load_theme(theme_name: str) -> dict:
    """prompts/themes/ 디렉토리에서 테마 JSON을 로드하고 캐싱."""
    cache_key = f"theme:{theme_name}"
    if cache_key in _cache:
        return _cache[cache_key]

    file_path = _THEMES_DIR / f"{theme_name}.json"
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    _cache[cache_key] = data
    return data


def list_themes() -> list[str]:
    """사용 가능한 테마 이름 목록을 반환."""
    if not _THEMES_DIR.exists():
        return []
    return [f.stem for f in _THEMES_DIR.glob("*.json")]


def get_game_config() -> dict:
    """game_config.json을 로드."""
    return load_prompt("game_config")


def get_story_template() -> dict:
    """story_template.json을 로드."""
    return load_prompt("story_template")


def _assemble_template(data: dict) -> str:
    """system_role + sections 배열을 하나의 template 문자열로 조립."""
    parts = [data["system_role"]]

    for section in data["sections"]:
        # raw 플래그가 있으면 헤더 없이 body만 삽입 (directives 등)
        if section.get("raw"):
            parts.append(section["body"])
            continue

        header = section["header"]
        parts.append(f"\n### {header} ###")

        body = section["body"]
        if isinstance(body, list):
            parts.append("\n".join(f"- {item}" for item in body))
        else:
            parts.append(body)

    return "\n".join(parts)


def get_rules() -> dict:
    """rules.json을 로드."""
    return load_prompt("rules")


def get_theme_builder_prompt() -> dict:
    """theme_builder.json을 로드."""
    return load_prompt("theme_builder")
