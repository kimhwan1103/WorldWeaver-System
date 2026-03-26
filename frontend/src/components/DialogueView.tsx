import { useState, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import type { NPCAction } from "../api/types";
import type { Language } from "../i18n";
import { t } from "../i18n";
import TypewriterText from "./TypewriterText";
import MarkdownText from "./MarkdownText";

interface Message {
  sender: "player" | "npc";
  text: string;
  action?: NPCAction | null;
  dispositionLabel?: string;
  dispositionChanged?: boolean;
}

interface Props {
  lang: Language;
  npcName: string;
  npcRole: string;
  dispositionLabel: string;
  messages: Message[];
  loading: boolean;
  onSend: (message: string) => void;
  onLeave: () => void;
}

export default function DialogueView({
  lang, npcName, npcRole, dispositionLabel, messages, loading, onSend, onLeave,
}: Props) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;
    onSend(input.trim());
    setInput("");
  };

  const renderAction = (action: NPCAction) => {
    switch (action.type) {
      case "give_item": return t(lang, "actionGiveItem", { npc: npcName, item: action.item || "" });
      case "give_quest": return t(lang, "actionGiveQuest", { quest: action.quest || "" });
      case "reveal_info": return t(lang, "actionRevealInfo", { info: action.info || "" });
      case "refuse": return t(lang, "actionRefuse", { npc: npcName });
      case "attack": return t(lang, "actionAttack", { npc: npcName });
      default: return null;
    }
  };

  return (
    <div className="dialogue-view">
      <div className="dialogue-header">
        <div className="npc-info">
          <h2>💬 {npcName}</h2>
          <span className="npc-role">{npcRole}</span>
          <span className="npc-disposition">{dispositionLabel}</span>
        </div>
        <button className="leave-btn" onClick={onLeave}>{t(lang, "leave")}</button>
      </div>

      <div className="dialogue-messages">
        {messages.map((msg, i) => (
          <motion.div
            key={i}
            className={`message ${msg.sender}`}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <div className="message-sender">
              {msg.sender === "player" ? t(lang, "you") : npcName}
            </div>
            <div className="message-text">
              {msg.sender === "npc" && i === messages.length - 1 ? (
                <TypewriterText text={msg.text} speed={20} />
              ) : msg.sender === "npc" ? (
                <MarkdownText text={msg.text} />
              ) : (
                msg.text
              )}
            </div>
            {msg.action && (
              <div className="message-action">{renderAction(msg.action)}</div>
            )}
            {msg.dispositionChanged && (
              <div className="disposition-change">
                {t(lang, "dispositionChange", { label: msg.dispositionLabel || "" })}
              </div>
            )}
          </motion.div>
        ))}
        {loading && (
          <motion.div
            className="message npc typing"
            animate={{ opacity: [0.4, 1, 0.4] }}
            transition={{ repeat: Infinity, duration: 1.2 }}
          >
            <div className="message-sender">{npcName}</div>
            <div className="message-text">...</div>
          </motion.div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <form className="dialogue-input" onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t(lang, "typeMessage")}
          disabled={loading}
          autoFocus
        />
        <button type="submit" disabled={loading || !input.trim()}>{t(lang, "send")}</button>
      </form>
    </div>
  );
}

export type { Message };
