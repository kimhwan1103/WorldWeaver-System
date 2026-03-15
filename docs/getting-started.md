# Getting Started

## 필수 조건

- Python 3.13 이상
- Google AI Studio API 키 ([발급 링크](https://aistudio.google.com/apikey))

## 설치

```bash
# 저장소 클론
git clone <repository-url>
cd WorldWeaver-System

# 가상환경 생성 및 활성화
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 의존성 설치
pip install -e .
```

## 환경 설정

프로젝트 루트에 `.env` 파일을 생성하고 Google API 키를 설정합니다:

```
GOOGLE_API_KEY=your_api_key_here
```

## 사용법

WorldWeaver는 두 가지 서브커맨드를 제공합니다:

### 1. 테마 자동 생성 (`build-theme`)

세계관 문서 폴더를 분석하여 테마 JSON을 자동 생성합니다.

```bash
# 기본 사용
python main.py build-theme --lore-dir lore_documents

# 테마 이름 직접 지정
python main.py build-theme --lore-dir lore_documents --theme-name mythology
```

내부 동작:
1. 문서 로드 → 청크 분할
2. 청크별 지식 그래프 추출 (LLM)
3. 그래프 병합 → `knowledge_graph.graphml` 저장
4. 병합된 그래프 → 테마 JSON 생성 (NPC 프로필 포함) → `prompts/themes/{name}.json` 저장

테마 빌더는 지식 그래프의 캐릭터/세력 노드를 분석하여 **NPC 프로필을 자동 생성**합니다:
- 캐릭터 노드에서 대화 가능한 NPC 후보 2~5명 선별
- 장소 노드와의 관계를 분석하여 스테이지(소속 장소) 배정
- NPC 성격, 말투, 역할, 초기 호감도, 트리거 조건 자동 설계

### 2. 게임 실행 (`play`)

생성된 테마를 로드하여 게임을 실행합니다.

```bash
# 인터랙티브 모드 (직접 플레이)
python main.py play --theme mythology

# 자동 데모 모드 (영웅 페르소나, 10씬)
python main.py play --theme mythology --mode auto --persona hero --scenes 10

# 악당 페르소나
python main.py play --theme mythology --mode auto --persona villain
```

### CLI 옵션 레퍼런스

#### `build-theme`

| 옵션 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `--lore-dir` | 예 | — | 세계관 문서 폴더 경로 |
| `--theme-name` | 아니오 | LLM이 결정 | 테마 식별자 (영문 소문자) |

#### `play`

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--theme` | `mythology` | 사용할 테마 |
| `--mode` | `interactive` | `interactive` 또는 `auto` |
| `--persona` | `hero` | 자동 모드 페르소나 |
| `--scenes` | `50` | 자동 모드 최대 씬 수 |

## 새로운 테마 만들기

### 방법 1: 자동 생성 (권장)

```bash
# 세계관 문서 폴더 준비
mkdir lore_scifi
# worldbuilding.txt, systems.txt 등 작성

# 테마 자동 생성
python main.py build-theme --lore-dir lore_scifi --theme-name scifi

# 플레이
python main.py play --theme scifi
```

### 방법 2: 수동 작성

`prompts/themes/mythology.json`을 참고하여 직접 작성할 수 있습니다. 필수 필드:

- `name` — 영문 식별자
- `display_name` — 표시 이름
- `initial_prompt` — 시작 시나리오
- `lore_dir` — 세계관 문서 경로
- `world_state_schema` — 게이지, 엔티티, 컬렉션 정의
- `rules` — 게이지 임계값 규칙
- `personas` — 페르소나 성향 매핑
- `npc_profiles` — NPC 프로필 목록 (선택, 상세 가이드: `docs/npc-system.md`)

## 그래프 시각화

게임 실행 후 생성된 `story_graph.graphml` 파일을 시각화합니다.

```bash
python visualize_graph.py
```

`assets/story_graph.png`로 이미지가 저장됩니다.

테마 빌더 실행 시 생성되는 `knowledge_graph.graphml`도 같은 방법으로 시각화할 수 있습니다.

## NPC 대화 시스템

게임 실행 중 NPC가 있는 스테이지에 진입하면, 선택지에 `💬 대화하기` 옵션이 나타납니다.

### 대화 흐름

1. 선택지에서 NPC 대화를 선택
2. 자유 텍스트 입력으로 NPC와 1:1 대화
3. NPC가 성격/말투/호감도에 맞는 응답 생성
4. 대화 중 NPC 행동 발생 가능:
   - 아이템 지급 → 인벤토리에 추가
   - 퀘스트 부여 → 미회수 복선에 추가
   - 비밀 공개 → RAG 메모리에 저장
5. `떠나기` 입력으로 대화 종료
6. 호감도가 월드 스테이트에 반영되어 이후 스토리에 영향

### NPC 주도 이벤트

특정 조건이 충족되면 NPC가 자동으로 등장합니다:
- 스토리 깊이 (예: 3번째 씬 이후)
- 게이지 임계값 (예: 타락 ≥ 0.6)
- 호감도 수준 (예: 0.6 이상일 때)
- 아이템 보유 (예: 특정 아이템 소지 시)

### NPC 프로필 수동 작성

테마 JSON에 `npc_profiles` 배열을 추가합니다:

```json
{
  "npc_profiles": [
    {
      "name": "카이론",
      "personality": "현명하고 차분한 현자. 비유로 가르치는 것을 선호한다.",
      "tone": "고풍스러운 존댓말. '~하였느니라', '~이니'와 같은 고어체.",
      "role": "현자",
      "stage": "별의 제단",
      "initial_disposition": 0.7,
      "trigger_conditions": [
        {
          "min_depth": 3,
          "min_disposition": 0.6,
          "directive": "카이론이 수호자에게 다가와 고대의 비밀을 알려주려 합니다."
        }
      ]
    }
  ]
}
```

자세한 NPC 시스템 설명은 [NPC 시스템 문서](npc-system.md)를 참고하세요.
