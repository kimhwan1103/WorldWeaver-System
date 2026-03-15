import { motion, AnimatePresence } from "framer-motion";
import type { Scene, Choice } from "../api/types";

interface Props {
  scene: Scene | null;
  choices: Choice[];
  loading: boolean;
  onChoice: (index: number) => void;
}

export default function StoryView({ scene, choices, loading, onChoice }: Props) {
  if (loading) {
    return (
      <div className="story-view loading">
        <motion.div
          className="loading-indicator"
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ repeat: Infinity, duration: 1.5 }}
        >
          장면 생성 중...
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
            <div className="scene-tags">
              <span className={`tag mood-${scene.features.mood.toLowerCase()}`}>
                {scene.features.mood}
              </span>
              <span className={`tag morality-${scene.features.morality_impact.toLowerCase()}`}>
                {scene.features.morality_impact}
              </span>
            </div>
          </div>

          <div className="scene-description">
            {scene.description.split("\n").map((p, i) => (
              <p key={i}>{p}</p>
            ))}
          </div>

          <div className="choices">
            <h3>선택지</h3>
            {choices.map((choice, i) => (
              <motion.button
                key={i}
                className={`choice-btn choice-${choice.choice_type}`}
                onClick={() => onChoice(i)}
                whileHover={{ scale: 1.02, x: 8 }}
                whileTap={{ scale: 0.98 }}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.1 }}
              >
                <span className="choice-icon">
                  {choice.choice_type === "dialogue" ? "💬" :
                   choice.choice_type === "combat" ? "⚔" : "▸"}
                </span>
                <span className="choice-text">{choice.text}</span>
                <span className="choice-feature">{choice.edge_feature}</span>
              </motion.button>
            ))}
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
