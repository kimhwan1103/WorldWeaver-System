import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { api } from "../api/client";
import type { ThemeInfo } from "../api/types";
import type { Language } from "../i18n";
import { t } from "../i18n";

interface LanguageOption {
  code: string;
  label: string;
}

interface Props {
  onStart: (theme: string, language: string) => void;
  onBuild: () => void;
  onLoad: (saveData: Record<string, unknown>) => void;
}

export default function TitleScreen({ onStart, onBuild, onLoad }: Props) {
  const [themes, setThemes] = useState<ThemeInfo[]>([]);
  const [selected, setSelected] = useState("");
  const [languages, setLanguages] = useState<LanguageOption[]>([]);
  const [selectedLang, setSelectedLang] = useState<Language>("ko");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.getThemes(), api.getLanguages()])
      .then(([themeRes, langRes]) => {
        setThemes(themeRes.themes);
        if (themeRes.themes.length > 0) setSelected(themeRes.themes[0].name);
        setLanguages(langRes.languages);
        setSelectedLang(langRes.default as Language);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const particles = Array.from({ length: 20 }, (_, i) => ({
    id: i,
    left: `${Math.random() * 100}%`,
    size: 2 + Math.random() * 4,
    duration: 6 + Math.random() * 8,
    delay: Math.random() * 5,
  }));

  return (
    <div className="title-screen">
      <div className="title-particles">
        {particles.map(p => (
          <span
            key={p.id}
            className="title-particle"
            style={{
              left: p.left,
              width: p.size,
              height: p.size,
              animationDuration: `${p.duration}s`,
              animationDelay: `${p.delay}s`,
            }}
          />
        ))}
      </div>
      <motion.div
        className="title-content"
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8 }}
      >
        <h1 className="game-title">{t(selectedLang, "title")}</h1>
        <p className="game-subtitle">{t(selectedLang, "subtitle")}</p>

        {loading ? (
          <p>{t(selectedLang, "loadingThemes")}</p>
        ) : (
          <div className="theme-selector">
            <h3>{t(selectedLang, "selectTheme")}</h3>
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
                  NPC {theme.npc_count} · Enemies {theme.enemy_count}
                </div>
              </motion.div>
            ))}

            {languages.length > 0 && (
              <div className="language-selector">
                <h3>{t(selectedLang, "selectLanguage")}</h3>
                <div className="language-options">
                  {languages.map((lang) => (
                    <button
                      key={lang.code}
                      className={`lang-btn ${selectedLang === lang.code ? "selected" : ""}`}
                      onClick={() => setSelectedLang(lang.code as Language)}
                    >
                      {lang.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <motion.button
              className="start-btn"
              onClick={() => selected && onStart(selected, selectedLang)}
              disabled={!selected}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              {t(selectedLang, "startGame")}
            </motion.button>

            <motion.button
              className="build-btn"
              onClick={onBuild}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              {t(selectedLang, "buildTheme")}
            </motion.button>

            <label className="load-btn-wrapper">
              <motion.span
                className="build-btn load-btn"
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                {t(selectedLang, "loadGame")}
              </motion.span>
              <input
                type="file"
                accept=".json"
                style={{ display: "none" }}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  const reader = new FileReader();
                  reader.onload = () => {
                    try {
                      const data = JSON.parse(reader.result as string);
                      onLoad(data);
                    } catch {
                      alert(t(selectedLang, "loadFailed"));
                    }
                  };
                  reader.readAsText(file);
                }}
              />
            </label>
          </div>
        )}
      </motion.div>
    </div>
  );
}
