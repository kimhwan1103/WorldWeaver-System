import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { Scene, Choice } from "../api/types";
import type { Language } from "../i18n";
import { t } from "../i18n";
import TypewriterText from "./TypewriterText";
import MarkdownText from "./MarkdownText";

interface Props {
  lang: Language;
  scene: Scene | null;
  choices: Choice[];
  loading: boolean;
  onChoice: (index: number) => void;
  endingAvailable?: boolean;
  onEnding?: () => void;
  onOpenMap?: () => void;
}

export default function StoryView({ lang, scene, choices, loading, onChoice, endingAvailable, onEnding, onOpenMap }: Props) {
  const [typingDone, setTypingDone] = useState(false);
  const [prevTitle, setPrevTitle] = useState("");

  useEffect(() => {
    if (scene && scene.title !== prevTitle) {
      setTypingDone(false);
      setPrevTitle(scene.title);
    }
  }, [scene, prevTitle]);

  const handleTypingComplete = useCallback(() => {
    setTypingDone(true);
  }, []);

  if (loading) {
    return (
      <div className="story-view loading">
        <motion.div
          className="loading-indicator"
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ repeat: Infinity, duration: 1.5 }}
        >
          {t(lang, "generating")}
        </motion.div>
      </div>
    );
  }

  if (!scene) return null;

  return (
    <div className="story-view">
      <AnimatePresence mode="wait">
        <motion.div
          key={scene.title}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          transition={{ duration: 0.5 }}
        >
          <div className="scene-header">
            <h2 className="scene-title">{scene.title}</h2>
            {scene.features && (
              <div className="scene-tags">
                {scene.features.mood && (
                  <span className={`tag mood-${scene.features.mood.toLowerCase()}`}>
                    {scene.features.mood}
                  </span>
                )}
                {scene.features.morality_impact && (
                  <span className={`tag morality-${scene.features.morality_impact.toLowerCase()}`}>
                    {scene.features.morality_impact}
                  </span>
                )}
              </div>
            )}
          </div>

          <div className="scene-description">
            {(scene.description || "").split("\n").filter(Boolean).map((p, i, arr) => (
              <div key={i}>
                {i === arr.length - 1 ? (
                  <TypewriterText
                    text={p}
                    speed={25}
                    onComplete={handleTypingComplete}
                  />
                ) : (
                  <MarkdownText text={p} />
                )}
              </div>
            ))}
          </div>

          <div className="choices">
            <div className="choices-header">
              <h3>{t(lang, "choices")}</h3>
              {typingDone && onOpenMap && (
                <button className="map-toggle-btn" onClick={onOpenMap}>
                  {t(lang, "worldMap")}
                </button>
              )}
            </div>
            {typingDone && choices.map((choice, i) => (
              <motion.button
                key={i}
                className={`choice-btn choice-${choice.choice_type}${choice.risky ? " choice-risky" : ""}`}
                disabled={loading}
                onClick={() => !loading && onChoice(i)}
                whileHover={{ scale: 1.02, x: 8 }}
                whileTap={{ scale: 0.98 }}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.1 }}
              >
                <span className="choice-icon">
                  {choice.risky ? "⚡" :
                   choice.choice_type === "dialogue" ? "💬" :
                   choice.choice_type === "combat" ? "⚔" : "▸"}
                </span>
                <span className="choice-text">{choice.text}</span>
                <span className="choice-feature">{choice.edge_feature}</span>
              </motion.button>
            ))}
          </div>

          {typingDone && endingAvailable && onEnding && (
            <motion.button
              className="ending-trigger-btn"
              onClick={onEnding}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5 }}
              whileHover={{ scale: 1.03 }}
            >
              {t(lang, "endingTrigger")}
            </motion.button>
          )}

          {!typingDone && (
            <button className="skip-typing-btn" onClick={() => setTypingDone(true)}>
              {t(lang, "skip") || "Skip ▸▸"}
            </button>
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
