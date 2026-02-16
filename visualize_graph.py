import networkx as nx
import matplotlib.pyplot as plt
from matplotlib import font_manager

# 한글 폰트 설정 (Windows)
font_path = "C:/Windows/Fonts/malgun.ttf"
font_prop = font_manager.FontProperties(fname=font_path)
plt.rcParams['font.family'] = font_prop.get_name()
plt.rcParams['axes.unicode_minus'] = False

# GraphML 파일 로드
G = nx.read_graphml("story_graph.graphml")

# 노드 라벨: title 속성이 있으면 사용, 없으면 ID를 15자로 줄임
labels = {}
for node in G.nodes():
    title = G.nodes[node].get('title', node)
    labels[node] = title if len(title) <= 18 else title[:18] + "..."

# 노드 색상: title 속성이 있는 노드(실제 씬)와 없는 노드(미래 선택지) 구분
node_colors = []
for node in G.nodes():
    if 'title' in G.nodes[node]:
        node_colors.append('#4A90D9')  # 실제 생성된 씬: 파란색
    else:
        node_colors.append('#A0A0A0')  # 미래 선택지: 회색

# 엣지 색상: 스토리 진행 vs 선택지 분기
edge_colors = []
for u, v, data in G.edges(data=True):
    if data.get('choice_text') == '이야기 진행':
        edge_colors.append('#2ECC71')  # 실제 진행 경로: 초록
    else:
        edge_colors.append('#E74C3C')  # 선택지 분기: 빨강

# 계층형 레이아웃
pos = nx.spring_layout(G, k=2.5, iterations=100, seed=42)

# 그래프 그리기
fig, ax = plt.subplots(figsize=(16, 10))
fig.patch.set_facecolor('#1A1A2E')
ax.set_facecolor('#1A1A2E')

# 엣지
nx.draw_networkx_edges(G, pos, edge_color=edge_colors, arrows=True,
                       arrowsize=15, width=1.5, alpha=0.7,
                       connectionstyle="arc3,rad=0.1")

# 노드
nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=800,
                       edgecolors='white', linewidths=1.5, alpha=0.9)

# 라벨
nx.draw_networkx_labels(G, pos, labels=labels, font_size=7,
                        font_color='white', font_family=font_prop.get_name())

# 범례
from matplotlib.lines import Line2D
legend_elements = [
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#4A90D9',
           markersize=12, label='생성된 씬 (Scene Node)'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#A0A0A0',
           markersize=12, label='미래 선택지 (Future Choice)'),
    Line2D([0], [0], color='#2ECC71', linewidth=2, label='스토리 진행 경로'),
    Line2D([0], [0], color='#E74C3C', linewidth=2, label='선택지 분기'),
]
ax.legend(handles=legend_elements, loc='upper left', fontsize=9,
          facecolor='#16213E', edgecolor='white', labelcolor='white',
          prop=font_prop)

ax.set_title('WorldWeaver System - Story Graph', fontsize=16,
             color='white', pad=20, fontweight='bold')
plt.tight_layout()

# 저장
plt.savefig('assets/story_graph.png', dpi=200, bbox_inches='tight',
            facecolor='#1A1A2E')
print("assets/story_graph.png 저장 완료")

plt.show()
