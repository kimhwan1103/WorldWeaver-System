import { useState, useCallback } from "react";
import { api } from "./api/client";
import type {
  GameView, WorldState, Scene, Choice, NPCInfo,
  CombatActionResponse, CombatResult,
} from "./api/types";
import type { Message } from "./components/DialogueView";
import TitleScreen from "./components/TitleScreen";
import StoryView from "./components/StoryView";
import CombatView from "./components/CombatView";
import DialogueView from "./components/DialogueView";
import Sidebar from "./components/Sidebar";
import "./App.css";

export default function App() {
  const [view, setView] = useState<GameView>("title");
  const [sessionId, setSessionId] = useState("");
  const [loading, setLoading] = useState(false);

  const [scene, setScene] = useState<Scene | null>(null);
  const [choices, setChoices] = useState<Choice[]>([]);
  const [worldState, setWorldState] = useState<WorldState | null>(null);
  const [npcs, setNpcs] = useState<NPCInfo[]>([]);
  const [sceneCount, setSceneCount] = useState(0);

  const [enemyName, setEnemyName] = useState("");
  const [enemyDesc, setEnemyDesc] = useState("");
  const [playerHp, setPlayerHp] = useState(0);
  const [playerMaxHp, setPlayerMaxHp] = useState(0);
  const [enemyHp, setEnemyHp] = useState(0);
  const [enemyMaxHp, setEnemyMaxHp] = useState(0);
  const [combatItems, setCombatItems] = useState<string[]>([]);
  const [combatLog, setCombatLog] = useState<CombatActionResponse[]>([]);
  const [combatResult, setCombatResult] = useState<CombatResult | null>(null);

  const [dialogueNpc, setDialogueNpc] = useState("");
  const [dialogueRole, setDialogueRole] = useState("");
  const [dialogueDisposition, setDialogueDisposition] = useState("");
  const [dialogueMessages, setDialogueMessages] = useState<Message[]>([]);

  const handleStart = useCallback(async (theme: string) => {
    setLoading(true);
    try {
      const res = await api.startGame(theme);
      setSessionId(res.session_id);
      setWorldState(res.world_state);
      const sceneRes = await api.generateScene(res.session_id, 0);
      setScene(sceneRes.scene);
      setChoices(sceneRes.choices);
      setWorldState(sceneRes.world_state);
      setNpcs(sceneRes.npcs || []);
      setSceneCount(sceneRes.scene_count);
      setView("story");
    } catch (e) {
      console.error(e);
      alert("게임 시작 실패");
    }
    setLoading(false);
  }, []);

  const handleChoice = useCallback(async (index: number) => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const res = await api.generateScene(sessionId, index);
      if (res.redirect === "dialogue" && res.npc_name) {
        await startDialogue(res.npc_name);
        setLoading(false);
        return;
      }
      if (res.redirect === "combat" && res.enemy_name) {
        await startCombat(res.enemy_name);
        setLoading(false);
        return;
      }
      setScene(res.scene);
      setChoices(res.choices);
      setWorldState(res.world_state);
      setNpcs(res.npcs || []);
      setSceneCount(res.scene_count);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  const startCombat = async (enemy: string) => {
    const res = await api.startCombat(sessionId, enemy);
    setEnemyName(res.enemy.name);
    setEnemyDesc(res.enemy.description || "");
    setPlayerHp(res.player.hp);
    setPlayerMaxHp(res.player.max_hp);
    setEnemyHp(res.enemy.hp);
    setEnemyMaxHp(res.enemy.max_hp);
    setCombatItems(res.available_items);
    setCombatLog([]);
    setCombatResult(null);
    setView("combat");
  };

  const handleCombatAction = useCallback(async (action: string, itemName?: string) => {
    setLoading(true);
    try {
      const res = await api.combatAction(sessionId, action, itemName);
      setPlayerHp(res.player_hp);
      setEnemyHp(res.enemy_hp);
      setCombatLog((prev) => [...prev, res]);
      if (res.combat_over && res.result) {
        setCombatResult(res.result);
        setWorldState(res.result.world_state);
      }
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }, [sessionId]);

  const handleCombatContinue = useCallback(() => {
    setCombatResult(null);
    setView("story");
    handleChoice(0);
  }, [handleChoice]);

  const startDialogue = async (npcName: string) => {
    const info = await api.getNpcInfo(sessionId, npcName);
    setDialogueNpc(info.name);
    setDialogueRole(info.role);
    setDialogueDisposition(info.disposition_label);
    setDialogueMessages([]);
    setView("dialogue");
  };

  const handleDialogueSend = useCallback(async (message: string) => {
    setDialogueMessages((prev) => [...prev, { sender: "player", text: message }]);
    setLoading(true);
    try {
      const res = await api.dialogue(sessionId, dialogueNpc, message);
      setDialogueMessages((prev) => [
        ...prev,
        {
          sender: "npc",
          text: res.response,
          action: res.action,
          dispositionLabel: res.disposition_label,
          dispositionChanged: res.disposition_changed,
        },
      ]);
      setDialogueDisposition(res.disposition_label);
      setWorldState(res.world_state);
      if (res.should_end) {
        setTimeout(() => setView("story"), 2000);
      }
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }, [sessionId, dialogueNpc]);

  if (view === "title") {
    return <TitleScreen onStart={handleStart} />;
  }

  return (
    <div className="game-layout">
      <main className="game-main">
        {view === "story" && (
          <StoryView scene={scene} choices={choices} loading={loading} onChoice={handleChoice} />
        )}
        {view === "combat" && (
          <CombatView
            enemyName={enemyName} enemyDescription={enemyDesc}
            playerHp={playerHp} playerMaxHp={playerMaxHp}
            enemyHp={enemyHp} enemyMaxHp={enemyMaxHp}
            availableItems={combatItems} combatLog={combatLog}
            combatResult={combatResult} loading={loading}
            onAction={handleCombatAction} onContinue={handleCombatContinue}
          />
        )}
        {view === "dialogue" && (
          <DialogueView
            npcName={dialogueNpc} npcRole={dialogueRole}
            dispositionLabel={dialogueDisposition} messages={dialogueMessages}
            loading={loading} onSend={handleDialogueSend}
            onLeave={() => setView("story")}
          />
        )}
      </main>
      <aside className="game-sidebar">
        <Sidebar worldState={worldState} npcs={npcs} sceneCount={sceneCount} />
      </aside>
    </div>
  );
}
