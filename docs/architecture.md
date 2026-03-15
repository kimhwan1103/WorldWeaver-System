# Architecture

> 최종 업데이트: v0.4.0

## 모듈 구조

```
main.py                         # CLI 진입점 (build-theme / play 서브커맨드)
worldweaver/
├── config.py                   # 시스템 설정 (game_config.json에서 로드)
├── models.py                   # Pydantic 모델 (StoryNode, Choice, NPCDialogueResponse)
├── prompt_loader.py            # JSON 설정 로더 (캐싱 지원)
├── rag.py                      # LoreMemory — FAISS 벡터 스토어 관리
├── chain.py                    # LCEL 체인 조립 (스토리 + NPC 대화)
├── graph.py                    # StoryGraph — NetworkX DiGraph + 이력 조회
├── world_state.py              # WorldState — 스키마 기반 동적 상태 관리 (NPC 관계도 포함)
├── rule_engine.py              # RuleEngine — 그래프 + 월드 스테이트 룰베이스 검증
├── npc_memory.py               # NPC 메모리 그래프 — 방향성 그래프 기반 기억 시스템
├── content_filter.py           # 입력 필터 + 주제 검증 + state_change 검증
├── llm_factory.py              # LLM 제공자 팩토리 (Groq, Google)
├── persona.py                  # 페르소나 기반 선택 전략
├── game.py                     # GameSession — 생성→검증→상태 업데이트 + NPC 대화 모드
└── theme_builder.py            # 지식 그래프 기반 테마 + NPC 자동 생성
prompts/
├── game_config.json            # LLM/RAG/게임 시스템 설정
├── story_template.json         # 스토리 생성 프롬프트 템플릿
├── npc_dialogue.json           # NPC 대화 생성 프롬프트 템플릿
├── rules.json                  # 공통 룰엔진 규칙 + 임계값
├── theme_builder.json          # 테마 빌더 프롬프트 (그래프 추출 / 테마 + NPC 생성)
└── themes/
    └── mythology.json          # 신화 테마 예시 (NPC 3명 포함)
lore_documents/
├── worldbuilding.txt           # 세계관 설정 문서
└── core_systems.txt            # 게임 메카닉 설계 문서
visualize_graph.py              # GraphML → PNG 시각화
```

## 설계 원칙

| 원칙 | 구현 |
|------|------|
| 테마 독립적 코드 | Python 코드에 테마 종속 문자열 없음. 전부 JSON에서 로드 |
| 스키마 기반 동적 구조 | WorldState의 게이지/엔티티/컬렉션을 테마 JSON이 정의 |
| 외부화된 프롬프트 | 모든 LLM 프롬프트와 규칙 메시지가 JSON에 분리 |
| 생성 → 검증 → 보정 루프 | 룰엔진이 사전 지시 + 사후 검증으로 세계관 무결성 보장 |

## 전체 데이터 흐름

### 테마 빌더 파이프라인

```
[세계관 문서 폴더]
        │
        ▼
[1] DirectoryLoader → 문서 로드
        │
        ▼
[2] RecursiveCharacterTextSplitter → 청크 분할
        │
        ▼
[3] 청크별 LLM 호출 → 부분 지식 그래프 추출
        │                (노드: character/location/item/system/concept/faction)
        │                (엣지: opposes/empowers/creates/triggers/guards/...)
        │
        ▼
[4] NetworkX DiGraph 병합
        │   같은 이름의 노드 → 하나로 합침 (설명은 더 긴 쪽 유지)
        │   → knowledge_graph.graphml 저장
        │
        ▼
[5] 병합된 그래프 → LLM → 테마 JSON 생성 (NPC 프로필 포함)
        │   캐릭터/세력 노드 → NPC 후보 선별 (2~5명)
        │   장소 노드 연결 → 스테이지 배정 (격리 기준)
        │   트리거 조건 자동 설계
        │
        ▼
[6] 검증 + 자동 보완 → prompts/themes/{name}.json 저장
        └── NPC 프로필 검증 (필수 필드, 호감도 범위, 트리거 유효성)
```

### 게임 세션 루프

```
[사용자 입력 / 페르소나 자동 선택]
        │
        ▼
   GameSession._generate_with_validation()
        │
        ├── ① RuleEngine.pre_generation_directives()
        │      ◄── WorldState (현재 상태 스냅샷)
        │      ◄── StoryGraph (이력: 깊이, 최근 분위기, 경로)
        │      ◄── 테마 rules (게이지 임계값, 절정 조건)
        │      → 강제 지시사항 생성 (프롬프트에 주입)
        │
        ├── ② LCEL Chain 호출
        │      ◄── RAG Retriever (세계관 + 누적 기억)
        │      ◄── WorldState.to_prompt_string()
        │      ◄── StoryGraph.get_recent_scenes_summary()
        │      ◄── WorldState.get_state_change_schema_for_prompt()
        │      → Gemini LLM → JsonOutputParser → StoryNode dict
        │
        ├── ③ RuleEngine.validate_scene()
        │      → 위반 발견 시 재생성 (최대 2회)
        │
        ├── ④ WorldState.apply_changes()        ── 상태 업데이트
        ├── ⑤ StoryGraph.add_scene()           ── 그래프 기록
        ├── ⑥ LoreMemory.add_memory()          ── RAG 기억 누적
        ├── ⑦ NPCManager.record_scene_event()  ── 해당 스테이지 NPC에 사건 기록
        └── ⑧ NPCManager._inject_npc_choices() ── 트리거된 NPC 대화 선택지 주입

   [NPC 대화 모드] (플레이어가 대화 선택지 선택 시)
        │
        ├── ① NPCMemoryGraph.to_prompt_context()
        │      ◄── NPC 프로필 (성격/말투/역할)
        │      ◄── 현재 호감도 (0.0~1.0)
        │      ◄── 스테이지 격리된 기억 (최근 5건)
        │
        ├── ② NPC Dialogue Chain 호출
        │      ◄── npc_context + world_state + dialogue_history + player_input
        │      → LLM → JsonOutputParser → NPCDialogueResponse dict
        │
        ├── ③ 호감도 업데이트 (disposition_delta 반영)
        ├── ④ NPC 행동 처리 (아이템 지급/퀘스트/정보 공개/거절/적대화)
        ├── ⑤ NPCMemoryGraph.record_dialogue() ── 대화 기억 기록
        └── ⑥ WorldState 동기화 ── 호감도 라벨을 entities에 반영
```

## 핵심 클래스

### WorldState (`world_state.py`)
**스키마 기반 동적 월드 스테이트.** 고정 필드 없이, 테마 JSON의 `world_state_schema`가 정의하는 구조를 동적으로 관리합니다.

- `entities` — 캐릭터, NPC 등 이름:상태 매핑
- `gauges` — 수치 게이지 (테마가 정의, 0.0~1.0)
- `properties` — 단일 속성 (현재 균열, 현재 시대 등)
- `collections` — 리스트형 데이터 (인벤토리, 방문 지역, 복선 등)

### RuleEngine (`rule_engine.py`)
**그래프 이력 + 월드 스테이트 조합 검증 엔진.** 두 단계로 작동합니다:

- **사전 지시** — 씬 생성 전, 현재 상태를 기반으로 LLM에 강제 지시사항 주입
  - 제거된 엔티티 재등장 금지
  - 게이지 임계값 규칙 (테마 JSON에서 로드)
  - 분위기 반복 방지 (그래프 이력)
  - 복선 회수 유도 (깊이 + 컬렉션)
- **사후 검증** — 생성된 씬이 규칙을 위반하는지 체크, 위반 시 재생성

### ThemeBuilder (`theme_builder.py`)
**지식 그래프 기반 테마 자동 생성기.** 세계관 문서를 청킹하여 각 청크에서 지식 그래프를 추출하고, 같은 이름의 노드를 연결점으로 병합한 뒤, 전체 그래프를 분석하여 테마 JSON을 생성합니다.

### StoryGraph (`graph.py`)
NetworkX DiGraph를 감싸는 래퍼. `title_uuid` 형식의 고유 노드 ID로 충돌을 방지합니다. 룰엔진이 사용하는 이력 조회 메서드를 제공합니다:
- `get_depth()` — 스토리 진행 깊이
- `get_recent_moods()` — 최근 N씬 분위기 목록
- `get_recent_scenes_summary()` — 최근 N씬 요약

### NPCMemoryGraph (`npc_memory.py`)
**방향성 그래프 기반 NPC 기억 시스템.** 각 NPC별 독립된 NetworkX DiGraph를 관리합니다.

- **노드** = 기억 단위 (dialogue / event / emotion / quest / observation)
- **엣지** = 인과 관계 (caused_by, follows, triggers)
- **스테이지 격리** — NPC는 자신의 소속 스테이지에서 발생한 사건만 기록/조회 가능
- **호감도** — 0.0~1.0 범위, 대화 내용에 따라 자동 변동 (적대적↔깊은 신뢰)
- `to_prompt_context()` — NPC 프로필 + 기억을 프롬프트 주입용 문자열로 변환
- `get_related_memories()` — 특정 기억과 인과적으로 연결된 기억을 BFS로 탐색

### NPCManager (`npc_memory.py`)
**게임 세션 내 모든 NPC의 메모리 그래프를 통합 관리.**

- 테마 JSON의 `npc_profiles`에서 NPC 로드
- `get_npcs_at_stage()` — 특정 스테이지에 존재하는 NPC 목록
- `record_scene_event()` — 씬 사건을 해당 스테이지의 모든 NPC에게 기록
- `get_triggered_npcs()` — NPC 주도 이벤트 조건 검사 (게이지/호감도/아이템/깊이)

### GameSession (`game.py`)
게임 루프를 관리합니다. 세 가지 모드를 지원합니다:
- **interactive** — 사용자가 직접 번호를 입력하여 선택
- **auto** — 페르소나(hero/villain)가 성향에 맞는 선택지를 자동 선택
- **NPC 대화 모드** — 선택지에서 대화를 선택하면 1:1 자유 대화 루프 진입

## 설정 분리 구조

```
코드 (테마 독립)              설정 (외부화)
─────────────────           ──────────────────
worldweaver/*.py             prompts/
  테마에 대해 아무것도          ├── game_config.json    ← 시스템 공통
  모르는 범용 코드              ├── story_template.json ← 스토리 프롬프트 템플릿
                              ├── npc_dialogue.json   ← NPC 대화 프롬프트 템플릿
                              ├── rules.json          ← 공통 규칙
                              ├── theme_builder.json   ← 테마 빌더 프롬프트
                              └── themes/
                                  └── {name}.json     ← 테마별 1파일 (NPC 포함)
```

## LCEL 체인 구성 (`chain.py`)

```python
chain = (
    {
        "context":              retriever.invoke(request),
        "request":              사용자 프롬프트,
        "world_state":          WorldState.to_prompt_string(),
        "recent_scenes":        StoryGraph.get_recent_scenes_summary(),
        "directives":           RuleEngine.pre_generation_directives(),
        "state_change_schema":  WorldState.get_state_change_schema_for_prompt(),
    }
    | prompt_template   # story_template.json에서 로드
    | llm               # Gemini 2.5-Flash
    | output_parser     # JSON → StoryNode dict
)
```

### NPC 대화 LCEL 체인 (`chain.py`)

```python
npc_chain = (
    {
        "npc_context":      NPCMemoryGraph.to_prompt_context(),
        "world_state":      WorldState.to_prompt_string(),
        "dialogue_history": NPCMemoryGraph.get_dialogue_history(),
        "player_input":     플레이어 대화 입력,
    }
    | prompt_template   # npc_dialogue.json에서 로드
    | llm               # Gemini 2.5-Flash
    | output_parser     # JSON → NPCDialogueResponse dict
)
```

### NPC 메모리 그래프 구조

```
NPCMemoryGraph (NPC별 독립 DiGraph)
│
├── dialogue_001 ──follows──→ dialogue_002 ──follows──→ dialogue_003
│                                  │
│                            caused_by
│                                  │
├── event_001 ─────────────────────┘
│
├── observation_001
│
└── quest_001

스테이지 격리:
  [별의 제단]                    [균열 계곡]
  ├── 카이론의 기억               ├── 에코의 기억
  │   ├── 대화 3건                │   ├── 대화 1건
  │   ├── 사건 5건                │   ├── 사건 3건
  │   └── 관찰 2건                │   └── 관찰 1건
  │                               └── 하데스의 사자의 기억
  │                                   ├── 거래 기록 2건
  │                                   └── 사건 3건
  │
  카이론은 균열 계곡의 사건을 모름 ✕
  에코는 별의 제단의 사건을 모름 ✕
```
