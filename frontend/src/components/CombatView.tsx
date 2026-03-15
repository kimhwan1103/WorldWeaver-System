import { useState } from "react";
import { motion } from "framer-motion";
import type { CombatActionResponse, CombatResult } from "../api/types";

interface Props {
  enemyName: string;
  enemyDescription: string;
  playerHp: number;
  playerMaxHp: number;
  enemyHp: number;
  enemyMaxHp: number;
  availableItems: string[];
  combatLog: CombatActionResponse[];
  combatResult: CombatResult | null;
  loading: boolean;
  onAction: (action: string, itemName?: string) => void;
  onContinue: () => void;
}

function HpBar({ current, max, label, color }: {
  current: number; max: number; label: string; color: string;
}) {
  const ratio = max > 0 ? current / max : 0;
  return (
    <div className="hp-bar-container">
      <div className="hp-label">{label}</div>
      <div className="hp-bar-bg">
        <motion.div
          className="hp-bar-fill"
          style={{ backgroundColor: color }}
          animate={{ width: `${ratio * 100}%` }}
          transition={{ duration: 0.5, ease: "easeOut" }}
        />
      </div>
      <div className="hp-text">{current} / {max}</div>
    </div>
  );
}

export default function CombatView({
  enemyName, enemyDescription, playerHp, playerMaxHp,
  enemyHp, enemyMaxHp, availableItems, combatLog,
  combatResult, loading, onAction, onContinue,
}: Props) {
  const [showItems, setShowItems] = useState(false);

  if (combatResult) {
    const outcomeText = {
      victory: "승리!", defeat: "패배...", flee: "도주 성공",
    };
    const outcomeClass = combatResult.outcome;

    return (
      <motion.div
        className={`combat-result ${outcomeClass}`}
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5 }}
      >
        <h2>{outcomeText[combatResult.outcome]}</h2>
        <div className="result-stats">
          <p>총 {combatResult.rounds}라운드</p>
          <p>가한 피해: {combatResult.damage_dealt}</p>
          <p>받은 피해: {combatResult.damage_taken}</p>
        </div>
        {combatResult.loot.length > 0 && (
          <div className="loot">
            <h3>획득 아이템</h3>
            {combatResult.loot.map((item, i) => (
              <span key={i} className="loot-item">✦ {item}</span>
            ))}
          </div>
        )}
        <button className="continue-btn" onClick={onContinue}>계속하기</button>
      </motion.div>
    );
  }

  return (
    <div className="combat-view">
      <div className="combat-header">
        <h2>⚔ {enemyName}</h2>
        {enemyDescription && <p className="enemy-desc">{enemyDescription}</p>}
      </div>

      <div className="combat-hp">
        <HpBar current={playerHp} max={playerMaxHp} label="수호자" color="#4ade80" />
        <HpBar current={enemyHp} max={enemyMaxHp} label={enemyName} color="#f87171" />
      </div>

      <div className="combat-log">
        {combatLog.slice(-3).map((log, i) => (
          <motion.div
            key={`${log.round}-${i}`}
            className="log-entry"
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
          >
            <div className="log-round">라운드 {log.round}</div>
            <div className="log-player">🗡 {log.player_action.detail}</div>
            {log.enemy_action.type !== "none" && (
              <div className="log-enemy">👹 {log.enemy_action.detail}</div>
            )}
          </motion.div>
        ))}
      </div>

      <div className="combat-actions">
        <button onClick={() => onAction("attack")} disabled={loading} className="action-btn attack">
          ⚔ 공격
        </button>
        <button onClick={() => onAction("defend")} disabled={loading} className="action-btn defend">
          🛡 방어
        </button>
        <button onClick={() => onAction("skill")} disabled={loading} className="action-btn skill">
          💥 강공격
        </button>
        {availableItems.length > 0 && (
          <div className="item-action">
            <button
              onClick={() => setShowItems(!showItems)}
              disabled={loading}
              className="action-btn item"
            >
              🧪 아이템
            </button>
            {showItems && (
              <div className="item-dropdown">
                {availableItems.map((item, i) => (
                  <button
                    key={i}
                    onClick={() => { onAction("item", item); setShowItems(false); }}
                  >
                    {item}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        <button onClick={() => onAction("flee")} disabled={loading} className="action-btn flee">
          🏃 도주
        </button>
      </div>
    </div>
  );
}
