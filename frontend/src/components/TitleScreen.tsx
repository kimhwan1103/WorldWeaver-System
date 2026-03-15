import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { api } from "../api/client";
import type { ThemeInfo } from "../api/types";

interface Props {
  onStart: (theme: string) => void;
}

export default function TitleScreen({ onStart }: Props) {
  const [themes, setThemes] = useState<ThemeInfo[]>([]);
  const [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getThemes()
      .then((res) => {
        setThemes(res.themes);
        if (res.themes.length > 0) setSelected(res.themes[0].name);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="title-screen">
      <motion.div
        className="title-content"
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8 }}
      >
        <h1 className="game-title">WorldWeaver</h1>
        <p className="game-subtitle">AI 기반 인터랙티브 스토리 엔진</p>

        {loading ? (
          <p>테마 로딩 중...</p>
        ) : (
          <div className="theme-selector">
            <h3>테마 선택</h3>
            {themes.map((theme) => (
              <motion.div
                key={theme.name}
                className={`theme-card ${selected === theme.name ? "selected" : ""}`}
                onClick={() => setSelected(theme.name)}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                <div className="theme-name">{theme.display_name}</div>
                <div className="theme-desc">{theme.description}</div>
                <div className="theme-meta">
                  NPC {theme.npc_count}명 · 적 {theme.enemy_count}종
                </div>
              </motion.div>
            ))}

            <motion.button
              className="start-btn"
              onClick={() => selected && onStart(selected)}
              disabled={!selected}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              모험 시작
            </motion.button>
          </div>
        )}
      </motion.div>
    </div>
  );
}
