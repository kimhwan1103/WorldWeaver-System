import { useState } from "react";
import { motion } from "framer-motion";
import { api } from "../api/client";
import type { WorldState, NPCInfo, Quest, Title } from "../api/types";
import type { Language } from "../i18n";
import { t } from "../i18n";

interface Props {
  lang: Language;
  worldState: WorldState | null;
  npcs: NPCInfo[];
  sceneCount: number;
  quests: Quest[];
  titles: Title[];
  sessionId: string;
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

const QUEST_STATUS_CONFIG: Record<Quest["status"], { icon: string; key: "questActive" | "questFading" | "questLost" | "questCompleted" }> = {
  active:    { icon: "🟢", key: "questActive" },
  fading:    { icon: "🟡", key: "questFading" },
  lost:      { icon: "🔴", key: "questLost" },
  completed: { icon: "✅", key: "questCompleted" },
};

export default function Sidebar({ lang, worldState, npcs, sceneCount, quests, titles, sessionId }: Props) {
  const [investigateMsg, setInvestigateMsg] = useState<string | null>(null);

  const handleInvestigate = async (itemName: string) => {
    try {
      const res = await api.investigateItem(sessionId, itemName);
      if (res.discovered) {
        setInvestigateMsg(`${t(lang, "hiddenFound")} ${itemName}`);
      } else {
        setInvestigateMsg(t(lang, "noHidden"));
      }
      setTimeout(() => setInvestigateMsg(null), 3000);
    } catch {
      setInvestigateMsg(t(lang, "noHidden"));
      setTimeout(() => setInvestigateMsg(null), 3000);
    }
  };

  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const handleSave = async () => {
    try {
      const data = await api.saveGame(sessionId);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `worldweaver_save_${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
      setSaveMsg(t(lang, "saveDone"));
      setTimeout(() => setSaveMsg(null), 3000);
    } catch {
      setSaveMsg("Save failed");
      setTimeout(() => setSaveMsg(null), 3000);
    }
  };

  if (!worldState) return null;

  const inventory = worldState.collections?.inventory || [];
  const entities = Object.entries(worldState.entities || {});

  return (
    <div className="sidebar">
      <div className="sidebar-section save-section">
        <button className="save-btn" onClick={handleSave}>
          {t(lang, "saveGame")}
        </button>
        {saveMsg && <span className="save-msg">{saveMsg}</span>}
      </div>
      <div className="sidebar-section">
        <h3>{t(lang, "status")}</h3>
        <div className="scene-counter">{t(lang, "scene")} #{sceneCount}</div>
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
        value && value !== "none" ? (
          <div key={key} className="sidebar-section property">
            <span className="property-label">{worldState.property_labels?.[key] || key}</span>
            <span className="property-value">{value}</span>
          </div>
        ) : null
      )}

      {entities.length > 0 && (
        <div className="sidebar-section">
          <h3>{t(lang, "characters")}</h3>
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
          <h3>{t(lang, "npcsHere")}</h3>
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
          <h3>{t(lang, "inventory")}</h3>
          {investigateMsg && (
            <motion.div
              className="investigate-msg"
              initial={{ opacity: 0, y: -5 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
            >
              {investigateMsg}
            </motion.div>
          )}
          <div className="inventory">
            {inventory.map((item, i) => (
              <div key={i} className="inventory-item-row">
                <span className="inventory-item-name">{item}</span>
                <button
                  className="investigate-btn"
                  onClick={() => handleInvestigate(item)}
                  title={t(lang, "investigate")}
                >
                  🔍
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {titles.length > 0 && (
        <div className="sidebar-section">
          <h3>{t(lang, "titles")}</h3>
          <div className="title-list">
            {titles.map((title) => (
              <motion.div
                key={title.id}
                className="title-entry"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
              >
                <div className="title-name">🏅 {title.name}</div>
                <div className="title-desc">{title.description}</div>
                {Object.keys(title.bonus).length > 0 && (
                  <div className="title-bonus">
                    {Object.entries(title.bonus).map(([stat, val]) => (
                      <span key={stat} className="title-bonus-tag">
                        {stat} +{val}
                      </span>
                    ))}
                  </div>
                )}
              </motion.div>
            ))}
          </div>
        </div>
      )}

      <div className="sidebar-section">
        <h3>{t(lang, "quests")}</h3>
        {quests.length === 0 ? (
          <div className="quest-empty">{t(lang, "questNoQuests")}</div>
        ) : (
          <div className="quest-list">
            {quests.map((quest) => {
              const cfg = QUEST_STATUS_CONFIG[quest.status];
              return (
                <motion.div
                  key={quest.id}
                  className={`quest-entry quest-${quest.status}`}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.3 }}
                >
                  <div className="quest-header">
                    <span className="quest-status-icon">{cfg.icon}</span>
                    <span className="quest-status-label">{t(lang, cfg.key)}</span>
                  </div>
                  <div className="quest-content">
                    {quest.status === "lost"
                      ? quest.content.slice(0, 8) + "...???"
                      : quest.status === "fading"
                        ? quest.content.slice(0, Math.max(15, quest.content.length - 10)) + "..."
                        : quest.content}
                  </div>
                  <div className="quest-npc">
                    {t(lang, "questFromNpc", { npc: quest.npc })}
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
