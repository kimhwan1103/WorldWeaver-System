import { motion } from "framer-motion";
import type { EndingResponse } from "../api/types";
import type { Language } from "../i18n";
import { t } from "../i18n";
import TypewriterText from "./TypewriterText";

interface Props {
  lang: Language;
  ending: EndingResponse;
  onReturn: () => void;
}

const TONE_STYLE: Record<string, { gradient: string; accent: string }> = {
  hopeful:     { gradient: "linear-gradient(135deg, #1a2a1a 0%, #0f1a0f 100%)", accent: "#4ade80" },
  triumphant:  { gradient: "linear-gradient(135deg, #2a2a1a 0%, #1a1a0f 100%)", accent: "#fbbf24" },
  tragic:      { gradient: "linear-gradient(135deg, #2a1a1a 0%, #1a0f0f 100%)", accent: "#f87171" },
  bittersweet: { gradient: "linear-gradient(135deg, #1a1a2a 0%, #0f0f1a 100%)", accent: "#a78bfa" },
  melancholic: { gradient: "linear-gradient(135deg, #1a1a1e 0%, #0f0f12 100%)", accent: "#60a5fa" },
};

export default function EndingView({ lang, ending, onReturn }: Props) {
  const style = TONE_STYLE[ending.tone] || TONE_STYLE.bittersweet;

  return (
    <motion.div
      className="ending-view"
      style={{ background: style.gradient }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 2 }}
    >
      <div className="ending-content">
        <motion.div
          className="ending-type-badge"
          style={{ borderColor: style.accent, color: style.accent }}
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5, duration: 1 }}
        >
          {t(lang, "endingLabel")} — {ending.ending_type.toUpperCase()}
        </motion.div>

        <motion.h1
          className="ending-title"
          style={{ color: style.accent }}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1, duration: 1.5 }}
        >
          {ending.title}
        </motion.h1>

        <motion.div
          className="ending-divider"
          style={{ backgroundColor: style.accent }}
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ delay: 2, duration: 1 }}
        />

        <motion.div
          className="ending-epilogue"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 2.5, duration: 1.5 }}
        >
          <TypewriterText text={ending.epilogue} speed={30} />
        </motion.div>

        <motion.p
          className="ending-final-line"
          style={{ color: style.accent }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 5, duration: 2 }}
        >
          {ending.final_line}
        </motion.p>

        <motion.button
          className="ending-return-btn"
          style={{ borderColor: style.accent, color: style.accent }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 7, duration: 1 }}
          onClick={onReturn}
          whileHover={{ scale: 1.05, backgroundColor: `${style.accent}22` }}
        >
          {t(lang, "endingReturn")}
        </motion.button>
      </div>
    </motion.div>
  );
}
