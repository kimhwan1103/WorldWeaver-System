# Changelog

이 프로젝트의 모든 주요 변경 사항을 기록합니다.
형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따르며, [Semantic Versioning](https://semver.org/lang/ko/)을 사용합니다.

## [0.5.0] - 2026-03-26

### Added
- **엔딩 시스템** (`worldweaver/ending.py`)
  - `EndingEvaluator` — 테마 JSON에 정의된 조건(스토리 깊이, 게이지, 퀘스트, NPC 호감도 등) 기반 멀티 엔딩 평가
  - `GameOverEvaluator` — 체력 고갈, 연속 전투 패배(3회+), 전원 적대화, 테마별 커스텀 게임오버 조건 평가
  - LLM 에필로그 생성을 위한 컨텍스트 빌더 (`build_ending_prompt_context`, `build_game_over_prompt_context`)
  - `EndingEpilogue`, `GameOverResponse` Pydantic 모델 추가
  - `prompts/ending_template.json` — 에필로그 생성 프롬프트 템플릿
- **세이브/로드 시스템** (`worldweaver/save_load.py`)
  - 전체 게임 세션 직렬화/역직렬화 (월드 스테이트, 스토리 그래프, NPC 메모리, 아이템 그래프, 내러티브 컨텍스트)
  - `save_to_file()` / `save_to_json_string()` 이중 내보내기
  - 로드 시 RAG 메모리, NPC 그래프, 아이템 그래프 완전 복원
- **아이템 그래프** (`worldweaver/item_graph.py`)
  - `ItemGraph` — 아이템 효과(attack, defense, max_hp, heal), 숨겨진 효과, NPC 친화도를 방향 그래프로 관리
  - 숨겨진 효과 발견 메커니즘: 직접 조사(`investigate_item`) 및 NPC 대화 통한 발견(`investigate_item_via_npc`)
  - NPC 친화도 시스템 — 아이템 소지에 따른 NPC 호감도 보정
  - **칭호/업적 시스템** — 조건(필수 아이템, 발견 수, 게이지, 엔티티) 충족 시 칭호 부여 + 스탯 보너스
- **판정 엔진** (`worldweaver/judgment.py`)
  - `JudgmentEngine` — 아이템 그래프, NPC 메모리, 스토리 그래프, 월드 스테이트, 칭호를 종합하여 선택지 결과를 확률적으로 판정
  - 기본 성공률 50%에 요인별 ±25% 가중치 (최종 범위 10%~95%)
  - 내러티브 힌트를 자연어로 생성하여 LLM 프롬프트에 주입 (수치 노출 없음)
  - `Choice` 모델에 `risky: bool` 필드 추가 — 위험한 선택지에만 판정 적용
- **다국어 지원 (i18n)**
  - `frontend/src/i18n.ts` — 한국어(ko), 영어(en), 일본어(ja) 번역 키
  - `worldweaver/translate.py` — `ThemeTranslator` 백엔드 테마 번역 래퍼
  - UI 전체 라벨, 게임 메커닉, NPC 액션, 호감도 표현 등 포괄적 번역
- **월드맵** (`frontend/src/components/WorldMap.tsx`)
  - SVG 기반 스테이지 노드-링크 시각화
  - 노드 상태: 현재 위치(펄스 효과), 방문 완료, 신규(파란색), 잠김(🔒)
  - NPC/적 아이콘 표시, 클릭으로 해금된 스테이지 이동
  - 호버 시 해금 힌트 및 위치 배지 툴팁
- **스테이지/장소 시스템** — 테마 JSON에 `stages` 정의
  - 다층(layer) 구조, 연결 관계, 해금 조건(퀘스트 완료/조건 트리거)
  - 방문 시 게이지 자동 변동, NPC/적 배치
  - `WebGameSession`에서 현재 스테이지 및 방문 이력 추적
- **테마 빌더 웹 UI** (`frontend/src/components/ThemeBuilder.tsx`)
  - 비밀번호 인증 후 접근 가능한 테마 생성 인터페이스
  - `.txt` 세계관 문서 업로드 → 빌드 진행률 폴링 → 결과 표시
  - API 엔드포인트: `/api/builder/auth`, `/api/builder/upload`, `/api/builder/start`, `/api/builder/status`
- **타자기 효과** (`frontend/src/components/TypewriterText.tsx`) — 글자 단위 텍스트 표시 애니메이션
- **마크다운 렌더링** (`frontend/src/components/MarkdownText.tsx`) — 내러티브 텍스트 리치 포맷 지원
- **엔딩/게임오버 뷰** (`EndingView.tsx`, `GameOverView.tsx`) — 톤별(희망적/비극적/씁쓸한/승리/우울) 그라데이션 배경 및 타자기 효과
- **synapse_collapse 테마** (`prompts/themes/synapse_collapse.json`) — SF/테크노스릴러 신규 테마
  - `lore_documents/synapse_collapse/`, `lore_documents/synapse_reckoning/` 세계관 문서 디렉토리

### Changed
- **API 서버** (`worldweaver/api/server.py`)
  - IP 기반 레이트 리미팅 (30 req/min) 추가
  - 일일 LLM 호출 쿼터 (기본 500회) 추가
  - 환경 변수 기반 CORS 설정
  - `logs/access.log` 접근 로깅
  - 글로벌 예외 핸들러 — 내부 오류 메시지 숨김
  - 신규 엔드포인트: `/api/game/ending`, `/api/game/save`, `/api/game/load`, `/api/game/investigate/{item_name}`
- **세션 매니저** (`worldweaver/api/session_manager.py`)
  - `WebGameSession`에 `translator`, `current_stage`, `visited_stages`, `item_graph`, `_narrative_context` 등 필드 추가
  - `generate_scene()` — 입력 인젝션 필터링, 위험한 선택지 판정 엔진 연동, 판정 내러티브 힌트 프롬프트 주입
  - 게임오버/엔딩 조건 자동 감지
- **테마 빌더** (`worldweaver/theme_builder.py`) — `stages`, `endings`, `game_over_conditions`, `titles`, `item_effects` 스키마 추가
- **전투 시스템** (`worldweaver/combat.py`) — 아이템 효과(attack, defense, max_hp) 반영, 전리품 아이템 그래프 등록
- **스토리 그래프** (`worldweaver/graph.py`) — 엔딩 평가용 이력 조회 메서드 추가
- **NPC 메모리** (`worldweaver/npc_memory.py`) — 아이템 그래프 연동, NPC 친화도 기반 호감도 보정
- **프론트엔드 전면 개편**
  - `App.tsx` — 게임 뷰 상태에 "ending", "gameover", "builder", "map" 추가, 세이브/로드 연동
  - `Sidebar.tsx` — 퀘스트(활성/소멸/실패/완료), 칭호, 아이템 조사, 월드맵 버튼 섹션 추가
  - `StoryView.tsx`, `CombatView.tsx`, `DialogueView.tsx` — 다국어 prop, 마크다운 렌더링 적용
  - `TitleScreen.tsx` — 언어 선택, 세이브 로드, 테마 빌더 진입 UI 추가
  - `App.css` — 엔딩/게임오버/테마빌더/월드맵/타자기 효과 등 대규모 스타일 추가
- `prompts/story_template.json` — 판정 힌트(`judgment_hint`) 슬롯 추가
- `prompts/theme_builder.json` — 스테이지, 엔딩, 게임오버, 칭호, 아이템 효과 생성 가이드 추가
- `prompts/game_config.json`, `prompts/rules.json`, `prompts/npc_dialogue.json` — 신규 시스템 연동 조정
- `Choice` 모델에 `choice_type`, `enemy_name`, `risky` 필드 추가

### Removed
- `prompts/themes/mythology.json` — 기존 그리스 신화 테마 삭제 (synapse_collapse로 대체)

## [0.4.0] - 2026-03-15

### Added
- **NPC 대화 시스템** — NPC와의 1:1 자유 대화 모드
  - 성격, 말투, 호감도를 가진 NPC가 캐릭터성을 유지하며 응답
  - NPC 행동: 아이템 지급(`give_item`), 퀘스트 부여(`give_quest`), 비밀 공개(`reveal_info`), 거절(`refuse`), 적대화(`attack`)
  - 대화 중 호감도 자동 변동 (-0.2 ~ +0.2)
  - NPC 대화 전용 LCEL 체인 (`build_npc_dialogue_chain()`)
  - NPC 대화 프롬프트 템플릿 (`prompts/npc_dialogue.json`)
- **NPC 메모리 그래프** (`npc_memory.py`)
  - 각 NPC별 독립 NetworkX DiGraph로 기억 관리
  - 기억 타입: dialogue, event, emotion, quest, observation
  - 기억 간 인과 관계(caused_by) 및 시간순 관계(follows) 엣지
  - **스테이지별 격리** — NPC는 자신의 소속 스테이지에서 발생한 사건만 기록/조회 가능
  - `NPCManager` — 게임 세션 내 전체 NPC 통합 관리
- **NPC 주도 이벤트** — 조건 기반 NPC 자동 등장
  - `trigger_conditions`: 게이지 임계값, 호감도 범위, 아이템 보유, 스토리 깊이 기반 트리거
  - 조건 충족 시 대화 선택지가 씬에 자동 주입
- **테마 빌더 NPC 자동 생성** — 세계관 문서에서 NPC 프로필 자동 생성
  - 지식 그래프의 캐릭터/세력 노드에서 2~5명 NPC 선별
  - 장소 노드 연결 분석으로 스테이지 자동 배정
  - `_validate_npc_profiles()` — NPC 프로필 필수 필드 검증 + 자동 보완
- `NPCDialogueResponse` Pydantic 모델 (`models.py`)
- `Choice` 모델에 `choice_type` (story/dialogue) 및 `npc_name` 필드 추가
- `mythology.json`에 NPC 3명 추가 (카이론/에코/하데스의 사자)

### Changed
- `game.py` — NPC 대화 모드 루프, NPC 선택지 주입, 스테이지 추적, 씬별 NPC 사건 기록 추가
- `chain.py` — `build_npc_dialogue_chain()` 함수 추가
- `main.py` — NPC 대화 체인 초기화 연동
- `world_state.py` — `to_summary_string()`에서 NPC 관계도와 일반 엔티티 분리 표시
- `theme_builder.py` — `SCHEMA_INSTRUCTIONS`에 `npc_profiles` 스키마 추가
- `theme_builder.json` — `generate_theme` 프롬프트에 NPC 생성 가이드라인 추가
- `story_template.json` — NPC 대화 선택지 생성 가이드 추가

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
