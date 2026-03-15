import json
from pathlib import Path

import networkx as nx
from langchain_community.document_loaders import DirectoryLoader
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_text_splitters import RecursiveCharacterTextSplitter

from worldweaver.config import CHUNK_OVERLAP, CHUNK_SIZE, LLM_MODEL
from worldweaver.prompt_loader import get_theme_builder_prompt

# 테마 JSON 출력 스키마 설명
SCHEMA_INSTRUCTIONS = """{
  "name": "string (영문 소문자, 공백 없음)",
  "display_name": "string (한글 테마 이름)",
  "description": "string (한글 1-2문장 설명)",
  "initial_prompt": "string (한글 도입 시나리오 3-5문장)",
  "lore_dir": "string (세계관 문서 폴더 경로)",
  "world_state_schema": {
    "entities": {
      "label": "string", "description": "string",
      "removed_statuses": ["string"]
    },
    "gauges": {
      "gauge_name": {
        "label": "string", "description": "string",
        "min": 0.0, "max": 1.0, "default": 0.0
      }
    },
    "properties": {
      "property_name": {
        "label": "string", "description": "string", "default": "string"
      }
    },
    "collections": {
      "collection_name": {
        "label": "string", "description": "string"
      }
    }
  },
  "rules": {
    "gauge_rules": [
      {"gauge": "string", "operator": ">=", "threshold": 0.0, "directive": "string"}
    ],
    "climax_rules": [
      {"min_depth": 8, "gauge": "string", "operator": ">=", "threshold": 0.0, "directive": "string"}
    ]
  },
  "personas": {
    "persona_name": ["string"]
  }
}"""


def build_theme_from_lore(lore_dir: Path, theme_name: str | None = None) -> dict:
    """세계관 문서 폴더를 분석하여 테마 JSON을 자동 생성.

    파이프라인: 문서 로드 → 청킹 → 청크별 그래프 추출 → 그래프 병합 → 테마 JSON 생성
    """
    prompts = get_theme_builder_prompt()
    llm = ChatGoogleGenerativeAI(model=LLM_MODEL)

    # ── 1단계: 문서 로드 + 청킹 ──
    print(f"[1/4] 세계관 문서 로드 중: {lore_dir}")
    loader = DirectoryLoader(str(lore_dir), glob="**/*.txt")
    docs = loader.load()
    if not docs:
        raise FileNotFoundError(f"'{lore_dir}' 폴더에서 .txt 파일을 찾을 수 없습니다.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    chunks = splitter.split_documents(docs)
    print(f"      문서 {len(docs)}개 → 청크 {len(chunks)}개로 분할")

    # ── 2단계: 각 청크에서 지식 그래프 추출 ──
    print(f"[2/4] 청크별 지식 그래프 추출 중 ({len(chunks)}개)...")
    extract_template = prompts["extract_graph"]["template"]
    partial_graphs = []

    for i, chunk in enumerate(chunks):
        print(f"      청크 {i + 1}/{len(chunks)} 분석 중...")
        prompt_text = extract_template.format(chunk_text=chunk.page_content)

        try:
            response = llm.invoke(prompt_text)
            graph_data = _parse_json_response(response.content)
            partial_graphs.append(graph_data)
            node_count = len(graph_data.get("nodes", []))
            edge_count = len(graph_data.get("edges", []))
            print(f"      → 노드 {node_count}개, 엣지 {edge_count}개 추출")
        except Exception as e:
            print(f"      → 청크 {i + 1} 분석 실패: {e}")
            continue

    if not partial_graphs:
        raise RuntimeError("모든 청크에서 그래프 추출에 실패했습니다.")

    # ── 3단계: 그래프 병합 ──
    print("[3/4] 지식 그래프 병합 중...")
    merged_graph = _merge_graphs(partial_graphs)
    print(
        f"      병합 완료: 노드 {merged_graph.number_of_nodes()}개, "
        f"엣지 {merged_graph.number_of_edges()}개"
    )

    # 병합된 그래프를 GraphML로 저장
    graph_output = lore_dir.parent / "knowledge_graph.graphml"
    nx.write_graphml(merged_graph, str(graph_output))
    print(f"      지식 그래프 저장: {graph_output}")

    # ── 4단계: 병합된 그래프 → 테마 JSON 생성 ──
    print("[4/4] 테마 JSON 생성 중...")
    nodes_by_type = _format_nodes_by_type(merged_graph)
    edges_summary = _format_edges_summary(merged_graph)
    document_summaries = _build_document_summaries(chunks)

    generate_template = prompts["generate_theme"]["template"]
    prompt_text = generate_template.format(
        node_count=merged_graph.number_of_nodes(),
        edge_count=merged_graph.number_of_edges(),
        nodes_by_type=nodes_by_type,
        edges_summary=edges_summary,
        schema_instructions=SCHEMA_INSTRUCTIONS,
        lore_dir=str(lore_dir),
        document_summaries=document_summaries,
    )

    response = llm.invoke(prompt_text)
    theme_data = _parse_json_response(response.content)

    if theme_name:
        theme_data["name"] = theme_name

    _validate_theme(theme_data)

    print(f"      테마 '{theme_data['display_name']}' 생성 완료")
    return theme_data


def save_theme(theme_data: dict, output_dir: Path | None = None) -> Path:
    """생성된 테마 JSON을 파일로 저장."""
    if output_dir is None:
        output_dir = Path(__file__).resolve().parent.parent / "prompts" / "themes"

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{theme_data['name']}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(theme_data, f, ensure_ascii=False, indent=2)

    print(f"테마 저장 완료: {output_path}")
    return output_path


# ── 내부 함수 ──


def _parse_json_response(raw_text: str) -> dict:
    """LLM 응답에서 JSON을 파싱. 마크다운 코드블록을 자동 제거."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    text = text.strip()
    return json.loads(text)


def _merge_graphs(partial_graphs: list[dict]) -> nx.DiGraph:
    """여러 부분 그래프를 하나의 NetworkX DiGraph로 병합.

    같은 이름의 노드는 하나로 합쳐지고, 설명은 더 긴 쪽을 유지한다.
    """
    merged = nx.DiGraph()

    for graph_data in partial_graphs:
        # 노드 병합
        for node in graph_data.get("nodes", []):
            name = node["name"]
            if merged.has_node(name):
                # 기존 노드가 있으면 설명이 더 긴 쪽을 유지
                existing_desc = merged.nodes[name].get("description", "")
                new_desc = node.get("description", "")
                if len(new_desc) > len(existing_desc):
                    merged.nodes[name]["description"] = new_desc
            else:
                merged.add_node(
                    name,
                    type=node.get("type", "concept"),
                    description=node.get("description", ""),
                )

        # 엣지 병합
        for edge in graph_data.get("edges", []):
            source = edge.get("source", "")
            target = edge.get("target", "")
            if not source or not target:
                continue

            # 소스/타겟 노드가 없으면 자동 추가
            if not merged.has_node(source):
                merged.add_node(source, type="concept", description="")
            if not merged.has_node(target):
                merged.add_node(target, type="concept", description="")

            # 같은 소스-타겟 엣지가 있어도 관계 유형이 다르면 추가
            if not merged.has_edge(source, target):
                merged.add_edge(
                    source,
                    target,
                    relation=edge.get("relation", "related_to"),
                    description=edge.get("description", ""),
                )

    return merged


def _format_nodes_by_type(graph: nx.DiGraph) -> str:
    """그래프 노드를 타입별로 정리한 문자열."""
    by_type: dict[str, list[str]] = {}
    for node, data in graph.nodes(data=True):
        node_type = data.get("type", "concept")
        desc = data.get("description", "")
        entry = f"{node}: {desc}" if desc else node
        by_type.setdefault(node_type, []).append(entry)

    lines = []
    type_labels = {
        "character": "캐릭터/존재",
        "location": "장소/지역",
        "item": "아이템/유물",
        "system": "시스템/메카닉",
        "concept": "개념/현상",
        "faction": "세력/집단",
    }
    for node_type, entries in sorted(by_type.items()):
        label = type_labels.get(node_type, node_type)
        lines.append(f"\n[{label}] ({len(entries)}개)")
        for entry in entries:
            lines.append(f"  - {entry}")

    return "\n".join(lines)


def _format_edges_summary(graph: nx.DiGraph) -> str:
    """그래프 엣지를 관계 유형별로 정리한 문자열."""
    by_relation: dict[str, list[str]] = {}
    for source, target, data in graph.edges(data=True):
        relation = data.get("relation", "related_to")
        desc = data.get("description", "")
        entry = f"{source} → {target}"
        if desc:
            entry += f" ({desc})"
        by_relation.setdefault(relation, []).append(entry)

    lines = []
    for relation, entries in sorted(by_relation.items()):
        lines.append(f"\n[{relation}] ({len(entries)}개)")
        for entry in entries:
            lines.append(f"  - {entry}")

    return "\n".join(lines)


def _build_document_summaries(chunks) -> str:
    """청크 원본 텍스트의 앞 200자씩을 요약으로 제공."""
    lines = []
    for i, chunk in enumerate(chunks):
        source = Path(chunk.metadata.get("source", "unknown")).name
        preview = chunk.page_content[:200].replace("\n", " ")
        lines.append(f"[{source} - 청크 {i + 1}] {preview}...")
    return "\n".join(lines)


def _validate_theme(data: dict):
    """테마 JSON의 필수 필드 존재 여부를 검증하고, 누락 필드를 자동 보완."""
    required_top = ["name", "display_name", "initial_prompt", "world_state_schema"]
    for field in required_top:
        if field not in data:
            raise ValueError(f"테마 JSON에 필수 필드 '{field}'가 없습니다.")

    # lore_dir이 없으면 기본값 설정
    if "lore_dir" not in data:
        print("(경고: 'lore_dir' 누락 → 기본값 'lore_documents' 설정)")
        data["lore_dir"] = "lore_documents"

    schema = data["world_state_schema"]
    required_schema = ["entities", "gauges", "collections"]
    for field in required_schema:
        if field not in schema:
            raise ValueError(f"world_state_schema에 필수 필드 '{field}'가 없습니다.")

    if "gauges" in schema and not schema["gauges"]:
        raise ValueError("최소 1개 이상의 게이지가 필요합니다.")

    # properties가 없으면 빈 dict로 초기화
    if "properties" not in schema:
        print("(경고: 'properties' 누락 → 빈 구조로 자동 추가)")
        schema["properties"] = {}

    # rules가 없으면 빈 구조로 초기화
    if "rules" not in data:
        print("(경고: 'rules' 누락 → 빈 구조로 자동 추가)")
        data["rules"] = {"gauge_rules": [], "climax_rules": []}

    # personas가 없으면 기본값 설정
    if "personas" not in data:
        print("(경고: 'personas' 누락 → 기본 hero/villain 설정)")
        data["personas"] = {
            "hero": ["Good", "Diplomatic", "Cautious"],
            "villain": ["Evil", "Aggressive"],
        }

    # 필수 컬렉션 자동 보완
    collections = schema.get("collections", {})
    required_collections = {
        "inventory": {"label": "보유 아이템", "description": "보유한 아이템 목록"},
        "resolved_events": {"label": "해결된 사건", "description": "해결된 사건 목록"},
        "unresolved_hooks": {"label": "미회수 복선", "description": "미회수 복선 목록"},
    }
    for col_name, default_val in required_collections.items():
        if col_name not in collections:
            print(f"(경고: 권장 컬렉션 '{col_name}' 누락 → 자동 추가)")
            collections[col_name] = default_val
