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
4. 병합된 그래프 → 테마 JSON 생성 → `prompts/themes/{name}.json` 저장

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

## 그래프 시각화

게임 실행 후 생성된 `story_graph.graphml` 파일을 시각화합니다.

```bash
python visualize_graph.py
```

`assets/story_graph.png`로 이미지가 저장됩니다.

테마 빌더 실행 시 생성되는 `knowledge_graph.graphml`도 같은 방법으로 시각화할 수 있습니다.
