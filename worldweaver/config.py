from pathlib import Path

from worldweaver.prompt_loader import get_game_config

_cfg = get_game_config()

# 경로
GRAPH_OUTPUT = Path(_cfg["game"]["graph_output"])

# RAG 설정
CHUNK_SIZE = _cfg["rag"]["chunk_size"]
CHUNK_OVERLAP = _cfg["rag"]["chunk_overlap"]

# LLM 설정
LLM_MODEL = _cfg["llm"]["model"]
EMBEDDING_MODEL = _cfg["llm"]["embedding_model"]

# 게임 설정
MAX_SCENES = _cfg["game"]["max_scenes"]
