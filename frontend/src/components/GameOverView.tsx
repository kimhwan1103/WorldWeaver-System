import { motion } from "framer-motion";
import type { GameOverResponse } from "../api/types";
import type { Language } from "../i18n";
import { t } from "../i18n";
import TypewriterText from "./TypewriterText";

interface Props {
  lang: Language;
  data: GameOverResponse;
  onReturn: () => void;
  onLoadSave: () => void;
}

export default function GameOverView({ lang, data, onReturn, onLoadSave }: Props) {
  return (
    <motion.div
      className="gameover-view"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 2 }}
    >
      <div className="gameover-content">
        <motion.div
          className="gameover-badge"
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.5, duration: 1 }}
        >
          {t(lang, "gameOver")}
        </motion.div>

        <motion.h1
          className="gameover-title"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1, duration: 1.5 }}
        >
          {data.title}
        </motion.h1>

        <motion.div
          className="gameover-cause"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.5, duration: 1 }}
        >
          {t(lang, "gameOverCause")}: {data.cause}
        </motion.div>

        <motion.div
          className="gameover-divider"
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ delay: 2, duration: 1 }}
        />

        <motion.div
          className="gameover-epilogue"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 2.5, duration: 1.5 }}
        >
          <TypewriterText text={data.epilogue} speed={30} />
        </motion.div>

        <motion.p
          className="gameover-final-line"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 5, duration: 2 }}
        >
          {data.final_line}
        </motion.p>

        <motion.div
          className="gameover-buttons"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 7, duration: 1 }}
        >
          <button className="gameover-btn gameover-btn-load" onClick={onLoadSave}>
            {t(lang, "gameOverLoad")}
          </button>
          <button className="gameover-btn gameover-btn-return" onClick={onReturn}>
            {t(lang, "gameOverReturn")}
          </button>
        </motion.div>
      </div>
    </motion.div>
  );
}
