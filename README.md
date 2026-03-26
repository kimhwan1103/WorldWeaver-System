# WorldWeaver

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![Node.js](https://img.shields.io/badge/Node.js-18%2B-339933?logo=node.js&logoColor=white)](https://nodejs.org)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangChain](https://img.shields.io/badge/LangChain-0.3-1C3C3C?logo=langchain&logoColor=white)](https://langchain.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Email](https://img.shields.io/badge/Email-rlaghks1103%40gmail.com-EA4335?logo=gmail&logoColor=white)](mailto:rlaghks1103@gmail.com)

> **[Demo](https://worldweaver-demo-production.up.railway.app)** | AI 기반 인터랙티브 스토리 엔진 — 세계관 문서만 넣으면 웹 브라우저에서 즐기는 텍스트 어드벤처
>
> **한국어** | [English](README_EN.md) | [日本語](README_JA.md)

<p align="center">
  <img src="docs/screenshots/title.png" alt="WorldWeaver 타이틀 화면" width="720" />
</p>

## 왜 만들었는가

텍스트 어드벤처 게임은 풍부한 서사를 전달할 수 있지만, 전통적인 방식에는 세 가지 근본적인 한계가 있습니다.

| 문제 | 설명 |
|------|------|
| **세계관마다 코드를 새로 짜야 한다** | 새로운 배경을 만들 때마다 스크립트, 분기, NPC를 수작업으로 구현해야 합니다. 세계관 문서는 있어도 그것을 게임으로 바꾸는 데 막대한 개발 비용이 듭니다. |
| **고정된 분기로는 몰입감에 한계가 있다** | 사전에 작성된 선택지만 제공하면 플레이어는 금방 패턴을 파악하고 몰입이 깨집니다. 매번 새로운 전개와 다양한 분기가 자동으로 생성되어야 진정한 리플레이 가치가 생깁니다. |
| **LLM 자유 생성만으로는 게임이 되지 않는다** | LLM에게 스토리를 맡기면 세계관과 맞지 않는 내용을 생성(환각)하거나, 비정형 텍스트를 뱉어 게임 시스템과 연동할 수 없습니다. |

**WorldWeaver는 이 세 가지를 동시에 해결합니다.**

- 세계관 문서 폴더만 넣으면 **지식 그래프 추출 → 테마 JSON 자동 생성**으로 코드 수정 없이 새로운 게임이 만들어지고,
- LLM이 매 씬마다 **세계관에 맞는 다양한 분기를 자동 생성**하여 플레이할 때마다 다른 전개를 경험할 수 있으며,
- **지식 그래프 + 룰엔진 + RAG + Pydantic 스키마**로 LLM 출력의 일관성과 정형성을 구조적으로 보장합니다.

```
세계관 문서 → 지식 그래프 추출 → 테마 JSON 자동 생성 → 웹 브라우저에서 플레이
```

## 주요 기능

### 게임 시스템

| 기능 | 설명 |
|------|------|
| **스토리 생성** | LLM이 매 씬마다 새로운 서사를 생성하고, 타이핑 애니메이션으로 표시 |
| **다양한 선택지** | 일반(▸), 대화(💬), 전투(⚔), 위험(⚡) 등 유형별 선택지 |
| **턴제 전투** | CombatView에서 공격/방어/강공격/아이템/도주 액션, HP바 실시간 표시 |
| **NPC 대화** | DialogueView에서 NPC와 자유 대화, 호감도 시스템, 퀘스트/아이템 부여 |
| **월드맵** | 스테이지 간 이동, 해금 조건(아이템/게이지), 현재 위치 애니메이션 |
| **인벤토리** | 전투 전리품 관리, 아이템 조사(🔍)로 히든 효과 발견 |
| **퀘스트 시스템** | 시간 경과에 따른 마모(active→fading→lost), NPC 대화로 복원 |
| **칭호 시스템** | 조건 충족 시 칭호 획득 + 보너스 효과 |
| **세이브/로드** | JSON 파일로 전체 게임 상태 저장/복원 (그래프 데이터 포함) |
| **다국어** | 한국어 / English / 日本語 UI 지원 |
| **엔딩/게임오버** | 조건부 엔딩 트리거, 패배 시 게임오버 화면 + 세이브 복원 |

### 엔진 핵심

- **지식 그래프 기반 테마 빌더** — 세계관 문서를 청킹 → 지식 그래프 추출 → 병합 → 테마 JSON + NPC 프로필 자동 생성
- **범용 테마 시스템** — 코드 수정 없이 JSON만으로 완전히 다른 세계관 구동
- **NPC 메모리 그래프** — NPC별 독립 방향성 그래프, 스테이지별 격리된 기억
- **그래프 + 룰베이스 검증** — 스토리 그래프 이력과 월드 스테이트를 조합한 무결성 검증
- **RAG 누적 기억** — 생성된 스토리가 벡터 스토어에 누적, 이전 사건 참조
- **동적 월드 스테이트** — 게이지/엔티티/컬렉션을 매 씬마다 LLM이 업데이트
- **구조화된 LLM 출력** — Pydantic 모델로 정형 데이터 변환

### 게임 화면

| 스토리 진행 + 사이드바 | 전투 시스템 |
|:---:|:---:|
| <img src="docs/screenshots/gameplay.png" width="400" /> | <img src="docs/screenshots/combat.png" width="400" /> |

| 월드맵 | 전투 승리 |
|:---:|:---:|
| <img src="docs/screenshots/worldmap.png" width="400" /> | <img src="docs/screenshots/victory.png" width="400" /> |

## 기술 스택

| 카테고리 | 기술 | 용도 |
|----------|------|------|
| **LLM** | Google Gemini 2.5-Flash | 스토리/대화/지식 그래프 생성 |
| **LLM 프레임워크** | LangChain (LCEL) | 파이프라인 오케스트레이션 |
| **벡터 검색** | FAISS + GoogleGenerativeAIEmbeddings | RAG 세계관 검색 + 누적 기억 |
| **백엔드** | FastAPI + Uvicorn | REST API + WebSocket |
| **프론트엔드** | React 19 + TypeScript 5.9 + Vite 8 | SPA 웹 클라이언트 |
| **UI 애니메이션** | Framer Motion | 타이핑 효과, 전환 애니메이션 |
| **마크다운 렌더링** | react-markdown | 스토리 텍스트 포맷팅 |
| **데이터 검증** | Pydantic v2 | LLM 출력 스키마 검증 |
| **그래프** | NetworkX | 스토리 분기 + 지식 그래프 + NPC 메모리 |

## 아키텍처

```
┌──────────────────────────────────────────────────────────────┐
│  Frontend (React + TypeScript)                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │TitleScreen│ │StoryView │ │CombatView│ │  DialogueView  │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ WorldMap  │ │ Sidebar  │ │EndingView│ │ GameOverView   │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────┘  │
└────────────────────────┬─────────────────────────────────────┘
                         │ REST API
┌────────────────────────▼─────────────────────────────────────┐
│  Backend (FastAPI)                                            │
│  ┌──────────────────┐  ┌──────────────────────────────────┐  │
│  │  SessionManager   │  │  WebGameSession                  │  │
│  │  (멀티 세션 관리) │  │  ├─ StoryChain (LCEL)            │  │
│  └──────────────────┘  │  ├─ NPCDialogueChain             │  │
│                        │  ├─ CombatEngine                  │  │
│                        │  ├─ WorldState                    │  │
│                        │  ├─ StoryGraph (NetworkX)         │  │
│                        │  ├─ RuleEngine                    │  │
│                        │  ├─ NPCManager + MemoryGraph      │  │
│                        │  ├─ ItemGraph                     │  │
│                        │  └─ LoreMemory (FAISS RAG)        │  │
│                        └──────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
         │                          │
    ┌────▼────┐              ┌──────▼──────┐
    │ Gemini  │              │  FAISS 벡터  │
    │  API    │              │   스토어     │
    └─────────┘              └─────────────┘
```

## 프로젝트 구조

```
WorldWeaver-System/
├── run_server.py                     # 백엔드 서버 실행
├── main.py                           # CLI 진입점 (build-theme / play)
│
├── worldweaver/                      # 핵심 엔진 패키지
│   ├── chain.py                      # LCEL 체인 (스토리 + NPC 대화)
│   ├── combat.py                     # 턴제 전투 엔진
│   ├── config.py                     # 시스템 설정
│   ├── content_filter.py             # 입력 필터 + 주제 검증
│   ├── ending.py                     # 엔딩/게임오버 로직
│   ├── game.py                       # GameSession (CLI 모드)
│   ├── graph.py                      # StoryGraph (NetworkX)
│   ├── item_graph.py                 # 아이템 그래프 + 히든 효과
│   ├── judgment.py                   # 위험 선택지 판정
│   ├── llm_factory.py                # LLM 프로바이더 팩토리
│   ├── models.py                     # Pydantic 데이터 모델
│   ├── npc_memory.py                 # NPC 메모리 그래프
│   ├── persona.py                    # 페르소나 선택 전략
│   ├── prompt_loader.py              # 프롬프트 JSON 로더
│   ├── rag.py                        # LoreMemory (FAISS)
│   ├── rule_engine.py                # 룰베이스 검증 엔진
│   ├── save_load.py                  # 세이브/로드 직렬화
│   ├── theme_builder.py              # 지식 그래프 기반 테마 자동 생성
│   ├── translate.py                  # 다국어 번역 시스템
│   ├── world_state.py                # 동적 월드 스테이트
│   └── api/
│       ├── server.py                 # FastAPI 서버 (REST + WebSocket)
│       └── session_manager.py        # 웹 게임 세션 관리
│
├── frontend/                         # 웹 프론트엔드
│   ├── src/
│   │   ├── App.tsx                   # 메인 앱 (뷰 라우팅 + 상태 관리)
│   │   ├── i18n.ts                   # 다국어 번역 (한/영/일)
│   │   ├── api/client.ts             # API 클라이언트
│   │   └── components/
│   │       ├── TitleScreen.tsx        # 타이틀 화면
│   │       ├── ThemeBuilder.tsx       # 세계관 문서 → 테마 생성 UI
│   │       ├── StoryView.tsx          # 스토리 뷰 (씬 + 선택지)
│   │       ├── CombatView.tsx         # 전투 뷰
│   │       ├── DialogueView.tsx       # NPC 대화 뷰
│   │       ├── WorldMap.tsx           # 월드맵 오버레이
│   │       ├── Sidebar.tsx            # 사이드바 (상태/인벤토리/퀘스트)
│   │       ├── EndingView.tsx         # 엔딩 화면
│   │       ├── GameOverView.tsx       # 게임오버 화면
│   │       ├── TypewriterText.tsx     # 타이핑 애니메이션
│   │       └── MarkdownText.tsx       # 마크다운 렌더링
│   └── package.json
│
├── prompts/                          # 외부화된 프롬프트/설정
│   ├── game_config.json              # 시스템 설정
│   ├── story_template.json           # 스토리 생성 프롬프트
│   ├── npc_dialogue.json             # NPC 대화 프롬프트
│   ├── ending_template.json          # 엔딩 생성 프롬프트
│   ├── rules.json                    # 룰엔진 규칙
│   ├── theme_builder.json            # 테마 빌더 프롬프트
│   └── themes/                       # 테마 JSON 파일
│       └── synapse_collapse.json
│
├── lore_documents/                   # 세계관 문서
│   ├── synapse_collapse/             # 테마별 원본 문서
│   ├── synapse_reckoning/
│   └── knowledge_graph.graphml       # 추출된 지식 그래프
│
├── docs/                             # 프로젝트 문서
└── pyproject.toml
```

## 실행 방법

### 필수 조건

- Python 3.12+
- Node.js 18+
- Google AI Studio API 키 ([발급 링크](https://aistudio.google.com/apikey))

### 설치

```bash
git clone <repository-url>
cd WorldWeaver-System

# 백엔드 설치
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .

# 프론트엔드 설치
cd frontend
npm install
cd ..
```

### 환경 설정

```bash
# .env 파일 생성
echo "GOOGLE_API_KEY=your_api_key_here" > .env
```

### 웹 게임 실행

```bash
# 1. 백엔드 서버 실행 (포트 8000)
python run_server.py

# 2. 프론트엔드 개발 서버 실행 (새 터미널, 포트 5173)
cd frontend
npm run dev
```

브라우저에서 **http://localhost:5173** 접속하여 게임을 즐길 수 있습니다.

### CLI 모드 실행

```bash
# 인터랙티브 모드 (터미널에서 직접 플레이)
python main.py play --theme mythology

# 자동 데모 모드
python main.py play --theme mythology --mode auto --persona hero --scenes 10
```

### 테마 자동 생성

세계관 문서 폴더만 준비하면 테마 JSON이 자동 생성됩니다:

```bash
# 1. 세계관 문서 폴더 준비
mkdir lore_scifi
# worldbuilding.txt, systems.txt 등 작성

# 2. 테마 자동 생성
python main.py build-theme --lore-dir lore_scifi --theme-name scifi

# 3. 생성된 테마로 플레이
python main.py play --theme scifi
```

웹 UI의 **"새 테마 만들기"** 버튼으로도 세계관 문서를 업로드하여 테마를 생성할 수 있습니다.

## 게임 플레이 가이드

### 기본 흐름

1. **타이틀 화면** — 테마 선택, 언어 선택, 모험 시작
2. **프롤로그** — AI가 생성한 세계관 인트로
3. **스토리 진행** — 씬 읽기 → 선택지 선택 → 다음 씬 생성 반복
4. **엔딩** — 조건 충족 시 엔딩 트리거

### 선택지 유형

| 아이콘 | 유형 | 설명 |
|--------|------|------|
| ▸ | 일반 | 스토리 진행 |
| 💬 | 대화 | NPC와 대화 모드 진입 |
| ⚔ | 전투 | 턴제 전투 모드 진입 |
| ⚡ | 위험 | 판정이 적용되는 고위험/고보상 선택지 |

### 전투 시스템

| 액션 | 효과 |
|------|------|
| ⚔ 공격 | 기본 공격 |
| 🛡 방어 | 방어력 1.5배, 피해 감소 |
| 💥 강공격 | 2배 피해, 대신 방어 취약 |
| 🎒 아이템 | 인벤토리 아이템 사용 |
| 🌟 도주 | 전투 탈출 시도 |

### 사이드바

우측 사이드바에서 실시간 게임 상태를 확인할 수 있습니다:

- **게이지 바** — 체력/오염/봉인 등 실시간 표시
- **캐릭터** — 처치한 적, NPC 호감도
- **NPC 목록** — 현재 장소의 NPC와 성향
- **인벤토리** — 보유 아이템 + 🔍 조사 기능
- **퀘스트** — 활성(🟢)/퇴색(🟡)/소실(🔴)/완료(✅)
- **세이브** — JSON 파일 다운로드

## 내부 아키텍처 상세

### 테마 빌더 파이프라인

```
[세계관 문서]
     │
     ▼
[문서 청킹] → 청크별 LLM 호출 → 부분 지식 그래프 추출
     │
     ▼
[그래프 병합] → 동일 이름 노드가 청크 간 연결점
     │
     ├── knowledge_graph.graphml (시각화 가능)
     ▼
[병합 그래프 → LLM] → 테마 JSON 생성
     │
     ├── NPC 후보 자동 선별 (2~5명)
     ├── 스테이지별 NPC 배정
     └── 트리거 조건 자동 설계
```

### 게임 세션 흐름

```
[선택지 클릭]
     │
     ├── 일반 → RuleEngine.pre_generation → LCEL Chain → RuleEngine.validate
     │         → WorldState.apply → StoryGraph.add → LoreMemory.add
     │
     ├── 전투 → CombatEngine.start → 턴 루프 → 결과 반영
     │
     ├── 대화 → NPCDialogueChain → 호감도/행동 처리 → WorldState 동기화
     │
     └── 위험 → JudgmentEngine.roll → 유리/불리 반영된 씬 생성
```

## 라이선스

MIT License
