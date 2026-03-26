import { motion } from "framer-motion";
import type { StageInfo } from "../api/types";
import type { Language } from "../i18n";
import { t } from "../i18n";

interface Props {
  lang: Language;
  stages: StageInfo[];
  loading: boolean;
  onTravel: (stageName: string) => void;
  onClose: () => void;
}

/** Layer별 Y 위치, 가로는 같은 레이어 내에서 분산 */
function getNodePosition(stage: StageInfo, allStages: StageInfo[]) {
  const sameLayer = allStages.filter((s) => s.layer === stage.layer);
  const idx = sameLayer.indexOf(stage);
  const count = sameLayer.length;

  const y = 80 + (stage.layer - 1) * 160;
  const totalWidth = count * 200;
  const startX = (600 - totalWidth) / 2 + 100;
  const x = startX + idx * 200;

  return { x, y };
}

export default function WorldMap({ lang, stages, loading, onTravel, onClose }: Props) {
  const positions = new Map<string, { x: number; y: number }>();
  stages.forEach((s) => positions.set(s.name, getNodePosition(s, stages)));

  // 연결선 생성
  const edges: { from: { x: number; y: number }; to: { x: number; y: number }; unlocked: boolean }[] = [];
  stages.forEach((stage) => {
    const fromPos = positions.get(stage.name);
    if (!fromPos) return;
    stage.connects_to.forEach((targetName) => {
      const toPos = positions.get(targetName);
      if (!toPos) return;
      // 중복 방지: 이름 순서로 한 방향만
      if (stage.name < targetName) {
        const target = stages.find((s) => s.name === targetName);
        edges.push({
          from: fromPos,
          to: toPos,
          unlocked: stage.unlocked && (target?.unlocked ?? false),
        });
      }
    });
  });

  return (
    <motion.div
      className="worldmap-overlay"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <div className="worldmap-container">
        <div className="worldmap-header">
          <h2>{t(lang, "worldMap")}</h2>
          <button className="worldmap-close" onClick={onClose}>
            {t(lang, "mapClose")} &times;
          </button>
        </div>

        <svg className="worldmap-svg" viewBox="0 0 600 600" preserveAspectRatio="xMidYMid meet">
          {/* 연결선 */}
          {edges.map((edge, i) => (
            <line
              key={i}
              x1={edge.from.x} y1={edge.from.y}
              x2={edge.to.x} y2={edge.to.y}
              stroke={edge.unlocked ? "rgba(167,139,250,0.4)" : "rgba(100,100,100,0.2)"}
              strokeWidth={edge.unlocked ? 2 : 1}
              strokeDasharray={edge.unlocked ? "none" : "6 4"}
            />
          ))}

          {/* 스테이지 노드 */}
          {stages.map((stage) => {
            const pos = positions.get(stage.name)!;
            const nodeClass = stage.is_current
              ? "current"
              : stage.unlocked && stage.visited
                ? "visited"
                : stage.unlocked
                  ? "new"
                  : "locked";

            return (
              <g key={stage.name} transform={`translate(${pos.x}, ${pos.y})`}>
                {/* 노드 원 */}
                <circle
                  r={stage.is_current ? 32 : 26}
                  className={`worldmap-node worldmap-node-${nodeClass}`}
                  onClick={() => {
                    if (stage.unlocked && !stage.is_current && !loading) {
                      onTravel(stage.name);
                    }
                  }}
                  style={{ cursor: stage.unlocked && !stage.is_current ? "pointer" : "default" }}
                />

                {/* 현재 위치 표시 */}
                {stage.is_current && (
                  <circle r={38} fill="none" stroke="var(--accent-light)" strokeWidth={2} opacity={0.5}>
                    <animate attributeName="r" values="34;40;34" dur="2s" repeatCount="indefinite" />
                    <animate attributeName="opacity" values="0.6;0.2;0.6" dur="2s" repeatCount="indefinite" />
                  </circle>
                )}

                {/* 잠금 아이콘 */}
                {!stage.unlocked && (
                  <text textAnchor="middle" dy="5" fontSize="18" fill="#666">🔒</text>
                )}

                {/* 미탐험 표시 */}
                {stage.unlocked && !stage.visited && !stage.is_current && (
                  <circle r={6} cx={20} cy={-20} fill="var(--info)" />
                )}

                {/* NPC/적 아이콘 */}
                {stage.npcs.length > 0 && (
                  <text x={-22} y={-22} fontSize="12">👤</text>
                )}
                {stage.enemies.length > 0 && (
                  <text x={12} y={-22} fontSize="12">⚔</text>
                )}

                {/* 이름 */}
                <text
                  textAnchor="middle"
                  dy={50}
                  className="worldmap-label"
                  fill={stage.unlocked ? "var(--text-primary)" : "var(--text-secondary)"}
                >
                  {stage.display_name}
                </text>

                {/* 상태 뱃지 */}
                {stage.is_current && (
                  <text textAnchor="middle" dy={66} fontSize="10" fill="var(--accent-light)">
                    {t(lang, "mapCurrent")}
                  </text>
                )}
                {!stage.unlocked && stage.unlock_hint && (
                  <text textAnchor="middle" dy={66} fontSize="9" fill="var(--text-secondary)">
                    {stage.unlock_hint}
                  </text>
                )}
                {stage.unlocked && !stage.visited && !stage.is_current && (
                  <text textAnchor="middle" dy={66} fontSize="10" fill="var(--info)">
                    {t(lang, "mapNew")}
                  </text>
                )}
              </g>
            );
          })}
        </svg>

        {loading && (
          <div className="worldmap-loading">
            <motion.div animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 1.5 }}>
              {t(lang, "generating")}
            </motion.div>
          </div>
        )}
      </div>
    </motion.div>
  );
}
