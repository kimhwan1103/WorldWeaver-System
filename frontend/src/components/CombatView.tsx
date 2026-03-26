import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { CombatActionResponse, CombatResult } from "../api/types";
import type { Language } from "../i18n";
import { t } from "../i18n";
import MarkdownText from "./MarkdownText";

interface Props {
  lang: Language;
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

interface DamagePopup {
  id: number;
  damage: number;
  target: "player" | "enemy";
  isCritical: boolean;
  x: number;
}

function HpBar({ current, max, label, color, lowHp }: {
  current: number; max: number; label: string; color: string; lowHp?: boolean;
}) {
  const ratio = max > 0 ? current / max : 0;
  return (
    <div className={`hp-bar-container ${lowHp ? "hp-low" : ""}`}>
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

let popupIdCounter = 0;

export default function CombatView({
  lang, enemyName, enemyDescription, playerHp, playerMaxHp,
  enemyHp, enemyMaxHp, availableItems, combatLog,
  combatResult, loading, onAction, onContinue,
}: Props) {
  const [showItems, setShowItems] = useState(false);
  const [shaking, setShaking] = useState(false);
  const [damagePopups, setDamagePopups] = useState<DamagePopup[]>([]);
  const [flashType, setFlashType] = useState<"" | "hit" | "critical">("");
  const prevLogLength = useRef(combatLog.length);

  // 새 전투 로그가 추가되면 이펙트 트리거
  useEffect(() => {
    if (combatLog.length > prevLogLength.current) {
      const latest = combatLog[combatLog.length - 1];
      const newPopups: DamagePopup[] = [];

      // 플레이어 공격 → 적에게 데미지
      if (latest.player_action.damage > 0) {
        const isCrit = latest.player_action.damage > 15;
        newPopups.push({
          id: popupIdCounter++,
          damage: latest.player_action.damage,
          target: "enemy",
          isCritical: isCrit,
          x: 30 + Math.random() * 40,
        });
      }

      // 적 공격 → 플레이어에게 데미지
      if (latest.enemy_action.damage > 0) {
        const isCrit = latest.enemy_action.damage > 15;
        newPopups.push({
          id: popupIdCounter++,
          damage: latest.enemy_action.damage,
          target: "player",
          isCritical: isCrit,
          x: 30 + Math.random() * 40,
        });

        // 피격 시 화면 흔들림
        setShaking(true);
        setFlashType(isCrit ? "critical" : "hit");
        setTimeout(() => {
          setShaking(false);
          setFlashType("");
        }, isCrit ? 500 : 300);
      }

      setDamagePopups((prev) => [...prev, ...newPopups]);

      // 팝업 자동 제거
      setTimeout(() => {
        setDamagePopups((prev) =>
          prev.filter((p) => !newPopups.find((np) => np.id === p.id))
        );
      }, 1200);
    }
    prevLogLength.current = combatLog.length;
  }, [combatLog]);

  const playerLowHp = playerMaxHp > 0 && playerHp / playerMaxHp < 0.3;

  if (combatResult) {
    const outcomeKey = combatResult.outcome as "victory" | "defeat" | "flee";
    const outcomeClass = combatResult.outcome;

    return (
      <motion.div
        className={`combat-result ${outcomeClass}`}
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, type: "spring", bounce: 0.3 }}
      >
        {outcomeClass === "victory" && (
          <div className="victory-particles">
            {[...Array(12)].map((_, i) => (
              <span key={i} className="victory-particle" style={{
                left: `${10 + Math.random() * 80}%`,
                animationDelay: `${Math.random() * 0.5}s`,
                animationDuration: `${1 + Math.random() * 1.5}s`,
              }} />
            ))}
          </div>
        )}
        <h2>{t(lang, outcomeKey)}</h2>
        <div className="result-stats">
          <p>{t(lang, "totalRounds", { n: combatResult.rounds })}</p>
          <p>{t(lang, "damageDealt")}: {combatResult.damage_dealt}</p>
          <p>{t(lang, "damageTaken")}: {combatResult.damage_taken}</p>
        </div>
        {combatResult.loot.length > 0 && (
          <div className="loot">
            <h3>{t(lang, "loot")}</h3>
            {combatResult.loot.map((item, i) => (
              <motion.span
                key={i}
                className="loot-item"
                initial={{ opacity: 0, scale: 0 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.3 + i * 0.15, type: "spring" }}
              >
                ✦ {item}
              </motion.span>
            ))}
          </div>
        )}
        <button className="continue-btn" onClick={onContinue}>{t(lang, "continue_")}</button>
      </motion.div>
    );
  }

  return (
    <div className={`combat-view ${shaking ? "screen-shake" : ""} ${playerLowHp ? "low-hp-warning" : ""}`}>
      {/* 피격 플래시 오버레이 */}
      <AnimatePresence>
        {flashType && (
          <motion.div
            className={`hit-flash ${flashType}`}
            initial={{ opacity: 0.6 }}
            animate={{ opacity: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
          />
        )}
      </AnimatePresence>

      <div className="combat-header">
        <h2>⚔ {enemyName}</h2>
        {enemyDescription && <MarkdownText text={enemyDescription} className="enemy-desc" />}
      </div>

      <div className="combat-hp">
        <div className="hp-bar-wrapper">
          <HpBar current={playerHp} max={playerMaxHp} label={t(lang, "player")} color="#4ade80" lowHp={playerLowHp} />
          {/* 플레이어 데미지 팝업 */}
          <AnimatePresence>
            {damagePopups.filter(p => p.target === "player").map(popup => (
              <motion.div
                key={popup.id}
                className={`damage-popup ${popup.isCritical ? "critical" : ""}`}
                style={{ left: `${popup.x}%` }}
                initial={{ opacity: 1, y: 0, scale: popup.isCritical ? 1.5 : 1 }}
                animate={{ opacity: 0, y: -60, scale: popup.isCritical ? 2 : 1.2 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 1, ease: "easeOut" }}
              >
                -{popup.damage}
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
        <div className="hp-bar-wrapper">
          <HpBar current={enemyHp} max={enemyMaxHp} label={enemyName} color="#f87171" />
          {/* 적 데미지 팝업 */}
          <AnimatePresence>
            {damagePopups.filter(p => p.target === "enemy").map(popup => (
              <motion.div
                key={popup.id}
                className={`damage-popup ${popup.isCritical ? "critical" : ""}`}
                style={{ left: `${popup.x}%` }}
                initial={{ opacity: 1, y: 0, scale: popup.isCritical ? 1.5 : 1 }}
                animate={{ opacity: 0, y: -60, scale: popup.isCritical ? 2 : 1.2 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 1, ease: "easeOut" }}
              >
                -{popup.damage}
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </div>

      <div className="combat-log">
        {combatLog.slice(-3).map((log, i) => (
          <motion.div
            key={`${log.round}-${i}`}
            className="log-entry"
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
          >
            <div className="log-round">{t(lang, "round")} {log.round}</div>
            <div className="log-player">🗡 <MarkdownText text={log.player_action.detail} inline /></div>
            {log.enemy_action.type !== "none" && (
              <div className="log-enemy">👹 <MarkdownText text={log.enemy_action.detail} inline /></div>
            )}
          </motion.div>
        ))}
      </div>

      <div className="combat-actions">
        <button onClick={() => onAction("attack")} disabled={loading} className="action-btn attack">
          {t(lang, "attack")}
        </button>
        <button onClick={() => onAction("defend")} disabled={loading} className="action-btn defend">
          {t(lang, "defend")}
        </button>
        <button onClick={() => onAction("skill")} disabled={loading} className="action-btn skill">
          {t(lang, "skill")}
        </button>
        {availableItems.length > 0 && (
          <div className="item-action">
            <button onClick={() => setShowItems(!showItems)} disabled={loading} className="action-btn item">
              {t(lang, "item")}
            </button>
            {showItems && (
              <div className="item-dropdown">
                {availableItems.map((item, i) => (
                  <button key={i} onClick={() => { onAction("item", item); setShowItems(false); }}>
                    {item}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        <button onClick={() => onAction("flee")} disabled={loading} className="action-btn flee">
          {t(lang, "fleeBattle")}
        </button>
      </div>
    </div>
  );
}
