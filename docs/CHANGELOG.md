# Changelog

이 프로젝트의 모든 주요 변경 사항을 기록합니다.
형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따르며, [Semantic Versioning](https://semver.org/lang/ko/)을 사용합니다.

## [0.3.0] - 2026-03-15

### Added
- **지식 그래프 기반 테마 빌더** (`theme_builder.py`)
  - 세계관 문서 청킹 → 청크별 지식 그래프 추출 → 병합 → 테마 JSON 자동 생성
  - `knowledge_graph.graphml` 중간 산출물 저장
  - 필수 필드 검증 + 누락 시 자동 보완
- **동적 월드 스테이트** (`world_state.py`)
  - 스키마 기반 동적 구조 (gauges / entities / properties / collections)
  - 테마 JSON이 정의하는 게이지/엔티티/컬렉션을 코드 수정 없이 사용
  - `state_change` 스키마를 LLM 프롬프트에 동적 주입
- **룰베이스 검증 엔진** (`rule_engine.py`)
  - 사전 지시: 제거된 엔티티 재등장 금지, 게이지 임계값, 분위기 반복 방지, 복선 회수 유도
  - 사후 검증: 위반 시 최대 2회 재생성
  - 테마별 규칙(gauge_rules, climax_rules)을 JSON에서 동적 로드
- **범용 테마 시스템**
  - `prompts/themes/{name}.json` 하나로 완전히 다른 세계관 구동
  - CLI에 `--theme` 옵션 추가
- **JSON 외부화** — 모든 프롬프트, 규칙, 설정을 JSON으로 분리
  - `prompts/game_config.json` — 시스템 공통 설정
  - `prompts/story_template.json` — 스토리 생성 프롬프트
  - `prompts/rules.json` — 공통 룰엔진 규칙
  - `prompts/theme_builder.json` — 테마 빌더 프롬프트
- `prompt_loader.py` — JSON 로더 유틸리티 (캐싱 지원)

### Changed
- `main.py`를 서브커맨드 방식으로 재설계 (`build-theme` / `play`)
- `chain.py` — 프롬프트에 `world_state`, `recent_scenes`, `directives`, `state_change_schema` 슬롯 추가
- `game.py` — 생성→검증→상태 업데이트 루프로 재작성
- `graph.py` — 이력 조회 메서드 추가 (`get_depth`, `get_recent_moods`, `get_recent_scenes_summary`)
- `models.py` — `StoryNode`에 `state_change: dict` 필드 추가 (테마별 동적 구조)
- `config.py` — `game_config.json`에서 로드, 테마 종속 항목 제거
- `persona.py` — `game_config.json` 의존 제거, 기본 페르소나 상수로 대체
- `rules.json` — 테마 종속 규칙 제거, 범용 용어 사용

### Fixed
- `rules.json`의 `{count}` 플레이스홀더가 채워지지 않던 버그
- `theme_builder.py` 검증에서 `lore_dir`, `properties`, `rules`, `personas` 누락 시 자동 보완

## [0.2.0] - 2026-03-15

### Changed
- 단일 스크립트(`stroy_generator_langchain.py`)를 `worldweaver/` 패키지로 모듈 분리
- `main.py`를 argparse 기반 진입점으로 재작성
- 프롬프트 영문법 오류 전면 수정
- `pyproject.toml`에 실제 dependencies 기재

### Added
- 인터랙티브 모드 — 사용자가 직접 선택지를 고르는 플레이 모드
- `docs/` 문서 폴더 신설

### Removed
- `stroy_generator.py` (레거시 Gemini 직접 호출 버전)
- `stroy_generator_langchain.py` (리팩토링으로 대체)
- 주석 처리된 테스트 코드 80줄+

### Fixed
- 노드 ID 충돌 문제 — title 대신 `title_uuid` 형식 사용
- 파일명 오타 (`stroy_` → 모듈 분리로 해소)

## [0.1.0] - 2026-03-15

### Added
- 초기 프로젝트 구현
- Google Gemini 직접 호출 방식 스토리 생성
- LangChain + RAG 기반 스토리 생성
- Pydantic 모델을 활용한 구조화된 LLM 출력
- FAISS 벡터 스토어 기반 세계관 RAG 검색
- NetworkX DiGraph 스토리 그래프 + GraphML 내보내기
- 페르소나 기반 자동 선택 (hero / villain)
- 누적 기억 시스템 (벡터 스토어에 스토리 추가)
- 세계관 문서 (`worldbuilding.txt`, `core_systems.txt`)
- 그래프 시각화 스크립트 (`visualize_graph.py`)
