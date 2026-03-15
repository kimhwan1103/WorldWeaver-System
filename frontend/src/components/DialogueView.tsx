import { useState, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import type { NPCAction } from "../api/types";

interface Message {
  sender: "player" | "npc";
  text: string;
  action?: NPCAction | null;
  dispositionLabel?: string;
  dispositionChanged?: boolean;
}

interface Props {
  npcName: string;
  npcRole: string;
  dispositionLabel: string;
  messages: Message[];
  loading: boolean;
  onSend: (message: string) => void;
  onLeave: () => void;
}

export default function DialogueView({
  npcName, npcRole, dispositionLabel, messages, loading, onSend, onLeave,
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

  return (
    <div className="dialogue-view">
      <div className="dialogue-header">
        <div className="npc-info">
          <h2>💬 {npcName}</h2>
          <span className="npc-role">{npcRole}</span>
          <span className="npc-disposition">{dispositionLabel}</span>
        </div>
        <button className="leave-btn" onClick={onLeave}>떠나기</button>
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
              {msg.sender === "player" ? "당신" : npcName}
            </div>
            <div className="message-text">{msg.text}</div>
            {msg.action && (
              <div className="message-action">
                {msg.action.type === "give_item" && `✦ ${npcName}이(가) '${msg.action.item}'을(를) 건네줍니다!`}
                {msg.action.type === "give_quest" && `✦ 새로운 퀘스트: ${msg.action.quest}`}
                {msg.action.type === "reveal_info" && `✦ 비밀: ${msg.action.info}`}
                {msg.action.type === "refuse" && `✦ ${npcName}이(가) 거절합니다.`}
                {msg.action.type === "attack" && `✦ ${npcName}이(가) 적대적으로 변합니다!`}
              </div>
            )}
            {msg.dispositionChanged && (
              <div className="disposition-change">호감도: {msg.dispositionLabel}</div>
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
          placeholder="대화를 입력하세요..."
          disabled={loading}
          autoFocus
        />
        <button type="submit" disabled={loading || !input.trim()}>전송</button>
      </form>
    </div>
  );
}

export type { Message };
