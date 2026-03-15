import { motion } from "framer-motion";
import type { WorldState, NPCInfo } from "../api/types";

interface Props {
  worldState: WorldState | null;
  npcs: NPCInfo[];
  sceneCount: number;
}

function GaugeBar({ name, label, value }: { name: string; label: string; value: number }) {
  const color = name === "health" ? "#4ade80"
    : name === "corruption" ? "#f87171"
    : name === "seal" ? "#60a5fa"
    : "#a78bfa";

  return (
    <div className="gauge">
      <div className="gauge-label">{label}</div>
      <div className="gauge-bar-bg">
        <motion.div
          className="gauge-bar-fill"
          style={{ backgroundColor: color }}
          animate={{ width: `${value * 100}%` }}
          transition={{ duration: 0.8 }}
        />
      </div>
      <div className="gauge-value">{(value * 100).toFixed(0)}%</div>
    </div>
  );
}

export default function Sidebar({ worldState, npcs, sceneCount }: Props) {
  if (!worldState) return null;

  const inventory = worldState.collections?.inventory || [];
  const entities = Object.entries(worldState.entities || {});

  return (
    <div className="sidebar">
      <div className="sidebar-section">
        <h3>📊 상태</h3>
        <div className="scene-counter">씬 #{sceneCount}</div>
        {Object.entries(worldState.gauges).map(([name, value]) => (
          <GaugeBar
            key={name}
            name={name}
            label={worldState.gauge_labels?.[name] || name}
            value={value}
          />
        ))}
      </div>

      {Object.entries(worldState.properties).map(([key, value]) =>
        value && value !== "없음" ? (
          <div key={key} className="sidebar-section property">
            <span className="property-label">
              {key === "active_rift" ? "활성 균열" : key}
            </span>
            <span className="property-value">{value}</span>
          </div>
        ) : null
      )}

      {entities.length > 0 && (
        <div className="sidebar-section">
          <h3>👥 캐릭터</h3>
          {entities.map(([name, status]) => (
            <div key={name} className={`entity entity-${status}`}>
              <span className="entity-name">{name}</span>
              <span className="entity-status">{status}</span>
            </div>
          ))}
        </div>
      )}

      {npcs.length > 0 && (
        <div className="sidebar-section">
          <h3>💬 이 장소의 NPC</h3>
          {npcs.map((npc) => (
            <div key={npc.name} className="npc-entry">
              <span className="npc-name">{npc.name}</span>
              <span className="npc-role">{npc.role}</span>
              <span className="npc-disp">{npc.disposition}</span>
            </div>
          ))}
        </div>
      )}

      {inventory.length > 0 && (
        <div className="sidebar-section">
          <h3>🎒 인벤토리</h3>
          <div className="inventory">
            {inventory.map((item, i) => (
              <div key={i} className="inventory-item">{item}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
