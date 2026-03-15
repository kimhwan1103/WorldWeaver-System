# NPC 시스템

> 방향성 그래프 기반 NPC 메모리 + 대화 + 주도 이벤트 시스템

## 개요

WorldWeaver의 NPC 시스템은 세 가지 핵심 기능으로 구성됩니다:

1. **NPC 대화** — 성격/말투/호감도를 가진 NPC와 1:1 자유 대화
2. **NPC 메모리 그래프** — 방향성 그래프 기반 기억 시스템 (스테이지별 격리)
3. **NPC 주도 이벤트** — 조건 기반 NPC 자동 등장 및 개입

## 아키텍처

### 모듈 구성

| 모듈 | 역할 |
|------|------|
| `npc_memory.py` | `NPCProfile`, `NPCMemoryGraph`, `NPCManager` 클래스 |
| `models.py` | `NPCDialogueResponse` Pydantic 모델, `Choice.choice_type`/`npc_name` 필드 |
| `chain.py` | `build_npc_dialogue_chain()` — NPC 대화 전용 LCEL 체인 |
| `game.py` | `_run_npc_dialogue()`, `_inject_npc_choices()`, `_handle_npc_action()` |
| `npc_dialogue.json` | NPC 대화 생성 프롬프트 템플릿 |
| `theme_builder.py` | `_validate_npc_profiles()` — NPC 프로필 검증 + 자동 보완 |

### 데이터 흐름

```
[테마 JSON: npc_profiles]
        │
        ▼
[NPCManager] ── NPC별 NPCMemoryGraph 초기화
        │
        ├── 씬 생성 시
        │   ├── get_triggered_npcs() → 트리거된 NPC 대화 선택지 주입
        │   └── record_scene_event() → 해당 스테이지 NPC에 사건 기록
        │
        └── 대화 선택 시
            ├── NPCMemoryGraph.to_prompt_context() → 프롬프트 구성
            ├── NPC Dialogue Chain → LLM → NPCDialogueResponse
            ├── record_dialogue() → 대화 기억 기록
            ├── _handle_npc_action() → 월드 스테이트 반영
            └── _sync_npc_disposition() → 호감도 동기화
```

## NPC 메모리 그래프

### 기억 노드 타입

| 타입 | 설명 | 예시 |
|------|------|------|
| `dialogue` | 플레이어와의 대화 | `[플레이어] 메두사를 어떻게 막죠? [카이론] 아테나의 방패를 찾아라...` |
| `event` | 씬에서 발생한 사건 | `[씬: 균열의 서막] 메두사의 석상들이 다가오고 있다` |
| `emotion` | NPC의 감정 변화 | `수호자의 용기에 감동받음` |
| `quest` | 부여하거나 완료한 퀘스트 | `아테나의 방패 탐색 퀘스트 부여` |
| `observation` | NPC의 관찰/메모 | `수호자는 신중한 성격으로 보임` |

### 엣지 관계

| 관계 | 설명 |
|------|------|
| `follows` | 시간순 연결 (같은 스테이지 내 기억 순서) |
| `caused_by` | 인과 관계 (이 기억이 다른 기억에 의해 발생) |

### 스테이지 격리

NPC는 자신의 **소속 스테이지에서 발생한 사건만 기억**합니다:

- 카이론(별의 제단) → 별의 제단에서 일어난 사건만 알고 있음
- 에코(균열 계곡) → 균열 계곡에서 일어난 사건만 알고 있음
- 별의 제단에서 메두사를 물리쳐도, 균열 계곡의 에코는 이 사실을 모름

이는 게임의 몰입감을 높이고, NPC가 전지적 시점을 가지는 것을 방지합니다.

```
record_memory(stage="균열 계곡")
  → 카이론(stage="별의 제단")은 기록하지 않음 (스테이지 불일치)
  → 에코(stage="균열 계곡")만 기록
```

### 호감도 시스템

| 범위 | 라벨 | NPC 태도 |
|------|------|----------|
| 0.8~1.0 | 깊은 신뢰 | 비밀 공유, 강력한 아이템 제공, 위기 시 도움 |
| 0.6~0.8 | 우호적 | 퀘스트 제공, 일반 정보 공유 |
| 0.4~0.6 | 중립 | 기본 대화, 거래 가능 |
| 0.2~0.4 | 경계 | 짧은 답변, 일부 요청 거절 |
| 0.0~0.2 | 적대적 | 대화 거부, 공격 가능성 |

호감도는 대화 내용에 따라 자동 변동합니다 (1회 대화당 -0.2 ~ +0.2).

## NPC 대화 시스템

### 대화 모드 진입

선택지에서 `💬 NPC이름(역할)과(와) 대화하기`를 선택하면 대화 모드에 진입합니다.

### 대화 루프

```
1. 플레이어 텍스트 입력
2. 인젝션 필터 (프롬프트 탈취 방지)
3. NPC 컨텍스트 구성:
   - NPC 프로필 (성격/말투/역할)
   - 현재 호감도
   - 이 스테이지에서의 최근 기억 5건
   - 대화 이력 5건
4. NPC 대화 LCEL 체인 호출
5. NPC 응답 출력
6. 호감도 업데이트
7. NPC 행동 처리 (있으면)
8. 대화 기억 기록
9. 자연스러운 종료 판단 → 반복 또는 종료
```

### NPC 행동 (action)

| 행동 | 효과 |
|------|------|
| `give_item` | 아이템을 `world_state.collections.inventory`에 추가 |
| `give_quest` | 퀘스트를 `world_state.collections.unresolved_hooks`에 추가 |
| `reveal_info` | 비밀 정보를 RAG 메모리에 저장 (향후 스토리에 반영) |
| `refuse` | NPC가 요청을 거절 (특별한 상태 변화 없음) |
| `attack` | NPC가 적대화 → `world_state.entities[NPC이름] = "적대"` |

### NPCDialogueResponse 모델

```python
class NPCDialogueResponse(BaseModel):
    response: str           # NPC의 대사 (1~3 단락)
    disposition_delta: float  # 호감도 변화량 (-0.2 ~ +0.2)
    action: str | None      # NPC 행동 (give_quest, give_item, ...)
    action_detail: str | None # 행동 상세 (퀘스트 내용, 아이템 이름 등)
    memory_note: str        # NPC가 기억할 이 대화의 요약
    should_end: bool        # 대화 자연 종료 여부
```

## NPC 주도 이벤트

### 트리거 조건

테마 JSON의 `trigger_conditions`로 정의합니다:

```json
{
  "trigger_conditions": [
    {
      "min_depth": 3,          // 최소 스토리 깊이
      "min_disposition": 0.6,  // 최소 호감도
      "max_disposition": 1.0,  // 최대 호감도
      "gauge": "corruption",   // 게이지 이름 (선택)
      "operator": ">=",        // 비교 연산자 (선택)
      "threshold": 0.6,        // 게이지 임계값 (선택)
      "requires_item": "명계의 동전",  // 필요 아이템 (선택)
      "directive": "카이론이 수호자에게 다가와 경고합니다."
    }
  ]
}
```

### 트리거 흐름

```
매 씬 생성 시:
  NPCManager.get_triggered_npcs()
    → 모든 NPC의 trigger_conditions 검사
    → 조건 충족된 NPC + directive 반환

  GameSession._inject_npc_choices()
    → 트리거된 NPC의 대화 선택지를 씬 선택지에 추가
    → 중복 방지 (같은 NPC 선택지가 이미 있으면 건너뜀)

  또한 directive가 RuleEngine 지시사항에도 주입됨
    → LLM이 NPC 등장을 씬 나레이션에 자연스럽게 반영
```

## 테마 빌더 NPC 자동 생성

`python main.py build-theme --lore-dir <폴더>` 실행 시 NPC 프로필이 자동 생성됩니다.

### 생성 로직

1. 지식 그래프의 **캐릭터/세력 노드**에서 대화 가능한 NPC 후보 2~5명 선별
2. **장소 노드**와의 관계를 분석하여 스테이지 배정
3. 역할에 따른 초기 호감도 자동 설정:
   - 동맹: 0.6~0.8
   - 중립: 0.4~0.5
   - 적대/의심: 0.1~0.3
4. NPC당 1~2개 트리거 조건 자동 설계

### 검증 및 자동 보완

`_validate_npc_profiles()`가 다음을 검증합니다:

| 필드 | 필수 | 누락 시 기본값 |
|------|------|----------------|
| `name` | 예 | (건너뜀) |
| `personality` | 아니오 | `"중립적인 성격의 인물."` |
| `tone` | 아니오 | `"평범한 말투"` |
| `role` | 아니오 | `"일반"` |
| `stage` | 아니오 | `"default"` |
| `initial_disposition` | 아니오 | `0.5` (범위: 0.0~1.0) |
| `trigger_conditions` | 아니오 | `[]` (`directive` 없는 항목 자동 제거) |

## NPC 프로필 작성 가이드

### 성격 (personality)

2~3문장으로 NPC의 성격, 동기, 특성을 설명합니다. LLM이 이를 참고하여 일관된 캐릭터성을 유지합니다.

```
좋은 예: "현명하고 차분한 반인반마 현자. 수천 년의 지혜를 가지고 있으며,
         직접적인 답보다 질문과 비유로 가르치는 것을 선호한다."

나쁜 예: "현명함"  ← 너무 짧아서 캐릭터성이 드러나지 않음
```

### 말투 (tone)

NPC의 대화 스타일을 구체적으로 묘사합니다. 예시 어미를 포함하면 효과적입니다.

```
좋은 예: "고풍스러운 존댓말. 비유와 신화적 언어를 자주 사용.
         '~하였느니라', '~이니'와 같은 고어체."

좋은 예: "반말과 존댓말을 섞어 쓰는 친근한 말투. 감탄사가 많고
         의성어/의태어를 자주 사용. '~거든!', '~란 말이야!'"
```

### 스테이지 (stage)

NPC의 소속 장소입니다. 씬의 제목이나 설명에 이 문자열이 포함되면 해당 스테이지로 인식됩니다. 세계관의 주요 장소 이름과 일치시켜야 합니다.

### 예시: mythology.json의 NPC 프로필

```json
[
  {
    "name": "카이론",
    "personality": "현명하고 차분한 반인반마 현자. 직접적인 답보다 비유로 가르침.",
    "tone": "고풍스러운 존댓말. '~하였느니라', '~이니'.",
    "role": "현자",
    "stage": "별의 제단",
    "initial_disposition": 0.7,
    "trigger_conditions": [
      {"min_depth": 3, "min_disposition": 0.6,
       "directive": "카이론이 고대의 비밀을 알려주려 합니다."},
      {"gauge": "corruption", "operator": ">=", "threshold": 0.6,
       "directive": "카이론이 타락의 기운을 감지하고 정화 의식을 제안합니다."}
    ]
  },
  {
    "name": "에코",
    "personality": "활발하고 호기심 많은 님프. 엉뚱하지만 핵심 정보를 우연히 흘린다.",
    "tone": "반말 섞인 친근한 말투. '~거든!', '~란 말이야!'",
    "role": "정보원",
    "stage": "균열 계곡",
    "initial_disposition": 0.5,
    "trigger_conditions": [
      {"min_depth": 2,
       "directive": "에코가 수풀 사이에서 나타나 이상한 현상을 알려주려 합니다."}
    ]
  },
  {
    "name": "하데스의 사자",
    "personality": "냉정하고 비즈니스적인 명계의 전령. 거래에는 정확하다.",
    "tone": "극존칭 정중하지만 차가운 말투. '~하시겠습니까', '~일 뿐입니다'.",
    "role": "상인",
    "stage": "균열 계곡",
    "initial_disposition": 0.3,
    "trigger_conditions": [
      {"requires_item": "명계의 동전",
       "directive": "하데스의 사자가 명계의 동전을 감지하고 거래를 제안합니다."}
    ]
  }
]
```

## WorldState 연동

### 호감도 동기화

대화 종료 시 NPC의 호감도 라벨이 `world_state.entities`에 자동 반영됩니다:

```
대화 전: world_state.entities = {"메두사": "적대"}
대화 후: world_state.entities = {"메두사": "적대", "카이론": "깊은 신뢰"}
```

### 요약 출력

`world_state.to_summary_string()`에서 NPC 관계도와 일반 엔티티가 분리 표시됩니다:

```
  활성 균열: 그리스 신화 | 타락 게이지: 0.3 | 봉인 게이지: 0.1
  캐릭터 상태: 메두사(적대)
  NPC 관계: 카이론(깊은 신뢰), 에코(우호적)
  보유 아이템: 수호자의 검
```
