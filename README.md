# WorldWeaver System

> Google Gemini와 LangChain을 활용한 AI 기반 신화 테마 게임 생성 프로젝트

## 프로젝트 소개

WorldWeaver System은 LangChain 프레임워크와 대규모 언어 모델(LLM)을 기반으로 실시간 텍스트형 게임을 구동하고 동적 스토리를 생성하는 프로젝트입니다. 플레이어의 입력이 발생할 때마다 AI가 실시간으로 다음 스토리, 선택지, 게임 메카닉을 추론하여 끊임없이 이어지는 상호작용형 게임 플레이 환경을 제공합니다.

게임의 구조는 방향 그래프(Directed Graph) 자료구조로 실시간 맵핑 및 관리됩니다. AI가 생성하는 개별 씬(Scene)은 노드(Node)로, 플레이어의 성향이 반영된 선택지는 엣지(Edge)로 구성됩니다. 이를 통해 게임이 진행될수록 상태 보존형 데이터가 누적되며, 무한히 분기되면서도 세계관의 논리적 무결성을 잃지 않는 정교한 게임 플레이를 구현합니다.

![스토리 그래프 시각화](assets/story_graph.png)

## 주요 기능

- **RAG 기반 스토리 생성** - 세계관 문서에서 관련 정보를 검색하여 맥락에 맞는 내러티브 생성
- **구조화된 LLM 출력** - Pydantic 모델로 LLM의 자유형 출력을 제목, 설명, 분위기, 선택지 등의 정형 데이터로 변환
- **분기형 내러티브 그래프** - NetworkX DiGraph로 스토리 노드와 선택 엣지를 관리, GraphML로 내보내기 지원
- **동적 선택지 조절** - 씬의 중요도에 따라 LLM이 자율적으로 2~5개의 선택지 생성
- **페르소나 기반 플레이** - 영웅/악당 페르소나에 따라 자동으로 성향에 맞는 선택지를 선호
- **누적 기억 시스템** - 생성된 스토리가 벡터 스토어에 지속 추가되어 이전 사건을 기억하고 참조

## 기술 스택

| 카테고리 | 기술 | 용도 |
|----------|------|------|
| LLM | Google Gemini 2.5-Flash | 스토리 내러티브 생성 |
| LLM 프레임워크 | LangChain (LCEL) | 파이프라인 오케스트레이션 |
| 임베딩 | GoogleGenerativeAIEmbeddings | 텍스트 벡터화 및 시맨틱 검색 |
| 데이터 검증 | Pydantic | LLM 출력 스키마 검증 |
| 그래프 | NetworkX | 스토리 분기 구조 관리 |
| 환경 관리 | python-dotenv | API 키 관리 |

## 아키텍처

### RAG 파이프라인

```
[세계관 문서 (lore_documents/)]
        │
        ▼
[텍스트 분할 (500자 청크, 50자 오버랩)]
        │
        ▼
[벡터 스토어 구축]
        │
        ├──── 검색 (Retriever) ◄── 사용자 프롬프트
        │            │
        │            ▼
        │     [관련 컨텍스트 추출]
        │            │
        │            ▼
        │     [프롬프트 템플릿에 주입]
        │            │
        │            ▼
        │     [Gemini LLM 호출]
        │            │
        │            ▼
        │     [JsonOutputParser → StoryNode]
        │            │
        │            ▼
        └──── [새로운 스토리를 벡터 스토어에 추가 (기억 누적)]
```

### LCEL 체인 구성

```python
chain = (
    {"context": retriever, "request": RunnablePassthrough()}
    | prompt_template      # 세계관 컨텍스트 + 요청을 결합
    | llm                  # Gemini 2.5-Flash
    | output_parser        # JSON → StoryNode 파싱
)
```

## 프로젝트 구조

```
game/
├── main.py                          # 진입점
├── stroy_generator.py               # 기본 스토리 생성 (Gemini 직접 호출)
├── stroy_generator_langchain.py     # RAG + LangChain 기반 고급 스토리 생성
├── story_graph.graphml              # 생성된 스토리 그래프 출력
├── lore_documents/
│   ├── core_systems.txt             # 게임 메카닉 설계 문서
│   └── worldbuilding.txt            # 세계관 설정 문서
├── pyproject.toml                   # 프로젝트 설정
├── .env                             # 환경 변수 (API 키)
└── .python-version                  # Python 3.13
```

## 데이터 모델

```python
class StoryNode(BaseModel):
    title: str           # 씬 제목 (예: "제1장: 균열의 서막")
    description: str     # 내러티브 본문 (2~3 단락)
    features: Features   # 씬 메타데이터
    choices: list[Choice] # 플레이어 선택지 (2~5개)

class Features(BaseModel):
    mood: str            # 분위기 (Tense, Mysterious, Hopeful 등)
    morality_impact: str # 도덕적 영향 (Good, Evil, Neutral)

class Choice(BaseModel):
    text: str            # 선택지 텍스트
    edge_feature: str    # 성향 (Aggressive, Diplomatic, Cautious)
    next_node_prompt: str # 다음 씬 생성을 위한 프롬프트
```

스토리 노드는 NetworkX의 방향 그래프에 추가되며, 각 선택지는 다음 노드를 향한 엣지로 저장됩니다. 최종 그래프는 GraphML 형식으로 내보내어 시각화할 수 있습니다.

## 세계관

태초의 **원초의 흐름(Primordial Flow)** 에서 세계가 탄생했으며, 이 흐름이 응축된 곳마다 서로 다른 이름이 붙었습니다. 올림포스의 화로, 위그드라실의 뿌리, 쿤룬의 봉우리, 두아트의 강, 티르 나 노그의 안개 등 모든 신화는 같은 기원의 서로 다른 기록입니다.

신들의 본질은 **봉인과 유물**로 흩어져 전해지지만, 시대가 흐르며 봉인이 약해질 때마다 **균열(Rift)** 이 열려 특정 신화의 논리로 현실을 재작성합니다. 이때 **별자리의 수호자**가 깨어나 성단 제단을 수호하고, 왜곡의 군대에 맞서 싸웁니다.

### 핵심 게임 시스템

- **균열 필드 (Rift Fields)** - 신화별 고유 규칙이 적용되는 전장
- **별자리 공명 (Constellation Resonance)** - 타워, 영웅, 유물 간 별자리 태그 기반 시너지
- **신화 계보 시너지** - 같은 신화 유닛 조합 시 교리 보너스
- **유물 & 의식** - 신화 아티팩트 장착 및 맵 전체 주문
- **타락 & 봉인 게이지** - 동적 난이도 조절 및 보스 약화 메커니즘
- **신화 연금술 (Mythic Alchemy)** - 서로 다른 신화의 유물을 융합

## 실행 방법

### 필수 조건

- Python 3.13 이상
- Google AI Studio API 키 ([발급 링크](https://aistudio.google.com/apikey))

### 설치

```bash
# 저장소 클론
git clone <repository-url>
cd game

# 가상환경 생성 및 활성화
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 의존성 설치
pip install langchain langchain-google-genai langchain-community langchain-text-splitters
pip install faiss-cpu networkx python-dotenv
```

### 환경 설정

`.env` 파일에 Google API 키를 설정합니다:

```
GOOGLE_API_KEY=your_api_key_here
```

### 실행

```bash
python stroy_generator_langchain.py
```

## 실행 예시

```
세계관 정보를 로드하여 RAG 메모리 구축 ....
RAG 구축 완료

========================================================
장면 생성 중 ....

[ 제1장: 균열의 서막 - 사자자리의 경고 ]
밤하늘의 사자자리(Leo)는 언제나 굳건한 빛을 발하며 별의 제단을 비추는
이정표였습니다. 하지만 오늘 밤, 그 웅장했던 빛이 미세하게 떨리더니 이내
눈에 띄게 약해지기 시작했습니다. 별자리의 수호자인 당신은 불길한 예감에
사로잡혔습니다. 이윽고, 눈앞의 평온했던 계곡이 마치 거대한 존재의 손에
찢겨 나가는 듯한 끔찍한 소리와 함께 균열이 벌어졌습니다. ...

(시스템 : 새로운 기억이 저장되었음)

--- 선택지 ---
1. 발밑의 신성한 광맥에 기초적인 감시탑을 건설하여 적의 움직임을 파악하고 방어선을 구축한다.
2. 사자자리의 약해진 빛을 감지하고, 별자리의 힘을 끌어와 신성한 광맥의 에너지를 증폭시킬 방법을 모색한다.
3. 메두사의 석상들에 맞서기 위해, 고대 기록을 되짚어 그리스 신화 속 메두사의 약점이나 대응 전략을 떠올린다.
4. 다가오는 첫 번째 파동에 직접 맞서 싸울 준비를 하며, 수호자의 무기를 들고 전방으로 나선다.

(시스템: 페르소나 선택 -> '메두사의 석상들에 맞서기 위해, 고대 기록을 되짚어...')
그래프가 'story_graph.graphml' 파일로 저장되었습니다. 노드 6개, 엣지 5개

========================================================
장면 생성 중 ....

[ 제2장: 석화의 그림자, 고대의 지혜 ]
사자자리의 빛은 여전히 불안하게 떨리고 있었고, 리프트에서 쏟아져 나온
메두사의 석상들은 침묵 속에서 마치 거대한 파도처럼 다가오고 있었다.

"메두사… 직접 눈을 마주치면 모든 것이 돌이 된다.
 하지만 페르세우스는… 방패에 비친 그림자를 이용해 그녀의 목을 베었다."

(시스템 : 새로운 기억이 저장되었음)

--- 선택지 ---
1. 주변에서 반사될 만한 물건을 찾거나, 신성한 광맥으로 급조할 방어구를 구상한다.
2. 메두사의 석화 능력 범위와 지속 시간, 그리고 석상들의 이동 속도에 대한 정보를 떠올려본다.
3. 보유한 신화 유물 중 메두사의 저주에 대항하거나, 약점을 공략할 수 있는 조합을 고민한다.
4. 스틱스 강물이나 신성한 광맥 등 변형된 지형지물을 활용하여 방어선을 구축하거나 함정을 설치할 방법을 모색한다.

(시스템: 페르소나 선택 -> '보유한 신화 유물 중 메두사의 저주에 대항하거나...')
그래프가 'story_graph.graphml' 파일로 저장되었습니다. 노드 11개, 엣지 10개
```
