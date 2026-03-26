import { useState, useCallback, useMemo, useEffect } from "react";
import { api, onApiError } from "./api/client";
import type {
  GameView, WorldState, Scene, Choice, NPCInfo, NPCGreeting,
  CombatActionResponse, CombatResult, Quest, EndingResponse,
} from "./api/types";
import type { Message } from "./components/DialogueView";
import type { Language } from "./i18n";
import { t } from "./i18n";
import TitleScreen from "./components/TitleScreen";
import ThemeBuilder from "./components/ThemeBuilder";
import StoryView from "./components/StoryView";
import CombatView from "./components/CombatView";
import DialogueView from "./components/DialogueView";
import EndingView from "./components/EndingView";
import GameOverView from "./components/GameOverView";
import WorldMap from "./components/WorldMap";
import Sidebar from "./components/Sidebar";
import "./App.css";

export default function App() {
  const [view, setView] = useState<GameView>("title");
  const [lang, setLang] = useState<Language>("ko");
  const [sessionId, setSessionId] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState("");

  // 토스트 알림
  const [toast, setToast] = useState<{ type: string; message: string } | null>(null);

  useEffect(() => {
    const unsub = onApiError((err) => {
      setToast(err);
      setTimeout(() => setToast(null), 8000);
    });
    return unsub;
  }, []);

  // 인트로 화면용
  const [introTitle, setIntroTitle] = useState("");
  const [introDescription, setIntroDescription] = useState("");
  const [introPrompt, setIntroPrompt] = useState("");

  const [scene, setScene] = useState<Scene | null>(null);
  const [choices, setChoices] = useState<Choice[]>([]);
  const [worldState, setWorldState] = useState<WorldState | null>(null);
  const [npcs, setNpcs] = useState<NPCInfo[]>([]);
  const [sceneCount, setSceneCount] = useState(0);
  const [quests, setQuests] = useState<Quest[]>([]);
  const [titles, setTitles] = useState<import("./api/types").Title[]>([]);
  const [mapStages, setMapStages] = useState<import("./api/types").StageInfo[]>([]);
  const [showMap, setShowMap] = useState(false);
  const [endingAvailable, setEndingAvailable] = useState(false);
  const [endingData, setEndingData] = useState<EndingResponse | null>(null);
  const [gameOverData, setGameOverData] = useState<import("./api/types").GameOverResponse | null>(null);

  const [enemyName, setEnemyName] = useState("");
  const [enemyDesc, setEnemyDesc] = useState("");
  const [playerHp, setPlayerHp] = useState(0);
  const [playerMaxHp, setPlayerMaxHp] = useState(0);
  const [enemyHp, setEnemyHp] = useState(0);
  const [enemyMaxHp, setEnemyMaxHp] = useState(0);
  const [combatItems, setCombatItems] = useState<string[]>([]);
  const [combatLog, setCombatLog] = useState<CombatActionResponse[]>([]);
  const [combatResult, setCombatResult] = useState<CombatResult | null>(null);

  const [dialogueNpc, setDialogueNpc] = useState("");    // 표시용 (번역된 이름)
  const [dialogueNpcKey, setDialogueNpcKey] = useState(""); // API용 (원본 이름)
  const [dialogueRole, setDialogueRole] = useState("");
  const [dialogueDisposition, setDialogueDisposition] = useState("");
  const [dialogueMessages, setDialogueMessages] = useState<Message[]>([]);

  const handleStart = useCallback(async (theme: string, language: string = "ko") => {
    setLang(language as Language);
    setLoading(true);
    setView("loading");
    setLoadingMessage(t(language as Language, "loadingSession"));
    try {
      const res = await api.startGame(theme, language);
      setSessionId(res.session_id);
      setWorldState(res.world_state);
      setIntroTitle(res.theme);
      setIntroDescription(res.description || "");
      setIntroPrompt(res.initial_prompt);

      setLoadingMessage(t(language as Language, "loadingScene"));
      const sceneRes = await api.generateScene(res.session_id, 0);
      setScene(sceneRes.scene);
      setChoices(sceneRes.choices);
      setWorldState(sceneRes.world_state);
      setNpcs(sceneRes.npcs || []);
      setSceneCount(sceneRes.scene_count);
      setQuests(sceneRes.quests || []);
      setEndingAvailable(sceneRes.ending_available || false);
      setTitles(sceneRes.titles || []);
      if (sceneRes.map) setMapStages(sceneRes.map.stages || []);
      setView("intro");
    } catch (e) {
      console.error(e);
      alert(t(language as Language, "startFailed"));
      setView("title");
    }
    setLoading(false);
  }, []);

  const handleChoice = useCallback(async (index: number) => {
    if (!sessionId || loading) return;
    setLoading(true);
    try {
      const res = await api.generateScene(sessionId, index);
      if (res.redirect === "dialogue" && res.npc_name) {
        await startDialogue(res.npc_name, res.greeting);
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
      setQuests(res.quests || []);
      setEndingAvailable(res.ending_available || false);
      setTitles(res.titles || []);
      if (res.map) setMapStages(res.map.stages || []);
      // 게임오버 감지
      if (res.game_over) {
        setLoading(false);
        triggerGameOver();
        return;
      }
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, loading]);

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
      // 매 라운드마다 사이드바 동기화
      if (res.world_state) {
        setWorldState(res.world_state);
      }
      if (res.combat_over && res.result) {
        setCombatResult(res.result);
        setWorldState(res.result.world_state);
        // 전투 후 게임오버 감지
        if (res.result.game_over) {
          setLoading(false);
          triggerGameOver();
          return;
        }
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

  const startDialogue = async (npcName: string, greeting?: NPCGreeting) => {
    if (greeting) {
      setDialogueNpc(greeting.npc_name);
      setDialogueNpcKey(greeting.npc_key || npcName); // 원본 이름 우선
      setDialogueRole(greeting.role);
      setDialogueDisposition(greeting.disposition_label);
      setDialogueMessages([{ sender: "npc", text: greeting.greeting }]);
    } else {
      const info = await api.getNpcInfo(sessionId, npcName);
      setDialogueNpc(info.name);
      setDialogueNpcKey(npcName); // getNpcInfo는 원본 이름으로 호출됨
      setDialogueRole(info.role);
      setDialogueDisposition(info.disposition_label);
      setDialogueMessages([]);
    }
    setView("dialogue");
  };

  const handleDialogueSend = useCallback(async (message: string) => {
    setDialogueMessages((prev) => [...prev, { sender: "player", text: message }]);
    setLoading(true);
    try {
      const res = await api.dialogue(sessionId, dialogueNpcKey || dialogueNpc, message);
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
      if (res.quests) setQuests(res.quests);
      if (res.should_end) {
        setTimeout(() => setView("story"), 2000);
      }
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }, [sessionId, dialogueNpc, dialogueNpcKey]);

  const handleTravel = useCallback(async (stageName: string) => {
    if (!sessionId) return;
    setLoading(true);
    setShowMap(false);
    try {
      const res = await api.travel(sessionId, stageName);
      setScene(res.scene);
      setChoices(res.choices);
      setWorldState(res.world_state);
      setNpcs(res.npcs || []);
      setSceneCount(res.scene_count);
      setQuests(res.quests || []);
      setEndingAvailable(res.ending_available || false);
      setTitles(res.titles || []);
      if (res.map) setMapStages(res.map.stages || []);
      setView("story");
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }, [sessionId]);

  // 게임오버 감지 → 게임오버 씬 생성
  const triggerGameOver = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setLoadingMessage(t(lang, "gameOverGenerating"));
    setView("loading");
    try {
      const res = await api.generateGameOver(sessionId);
      setGameOverData(res);
      setView("gameover");
    } catch (e) {
      console.error(e);
      setView("story");
    }
    setLoading(false);
  }, [sessionId, lang]);

  const handleLoad = useCallback(async (saveData: Record<string, unknown>) => {
    setLoading(true);
    setView("loading");
    setLoadingMessage(t(lang, "loadingSession"));
    try {
      const res = await api.loadGame(saveData);
      setSessionId(res.session_id);
      setWorldState(res.world_state);
      setChoices(res.choices || []);
      setNpcs(res.npcs || []);
      setSceneCount(res.scene_count);
      setQuests(res.quests || []);
      setTitles(res.titles || []);
      setEndingAvailable(res.ending_available || false);
      if (res.map) setMapStages(res.map.stages || []);
      if (res.meta?.language) setLang(res.meta.language as import("./i18n").Language);

      // 로드: 마지막 씬 데이터가 있으면 그대로 복원
      if (res.last_scene?.scene) {
        setScene(res.last_scene.scene);
        setChoices(res.last_scene.choices || res.choices || []);
      } else if (res.choices && res.choices.length > 0) {
        // last_scene 없으면 선택지만 표시
        setScene({
          title: "",
          description: "",
          features: { mood: "", morality_impact: "" },
          choices: res.choices,
          state_change: {},
        });
      }
      setView("story");
    } catch (e) {
      console.error(e);
      alert(t(lang, "loadFailed"));
      setView("title");
    }
    setLoading(false);
  }, [lang]);

  const handleEnding = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setLoadingMessage(t(lang, "endingGenerating"));
    setView("loading");
    try {
      const res = await api.generateEnding(sessionId);
      setEndingData(res);
      setView("ending");
    } catch (e) {
      console.error(e);
      setView("story");
    }
    setLoading(false);
  }, [sessionId, lang]);

  const handleEndingReturn = useCallback(() => {
    setView("title");
    setSessionId("");
    setScene(null);
    setChoices([]);
    setWorldState(null);
    setQuests([]);
    setTitles([]);
    setEndingData(null);
    setEndingAvailable(false);
    setSceneCount(0);
  }, []);

  const atmosphereClass = useMemo(() => {
    if (view === "combat") return "atmosphere-combat";
    if (view === "dialogue") return "atmosphere-dialogue";
    if (scene?.features?.mood) {
      const mood = scene.features.mood.toLowerCase();
      if (mood === "tense" || mood === "dark") return "atmosphere-tense";
      if (mood === "mysterious") return "atmosphere-mysterious";
      if (mood === "hopeful" || mood === "peaceful") return "atmosphere-hopeful";
    }
    return "atmosphere-default";
  }, [view, scene]);

  const toastOverlay = toast && (
    <div className={`toast-overlay toast-${toast.type}`} onClick={() => setToast(null)}>
      <div className="toast-icon">
        {toast.type === "rateLimit" ? "⚠" : toast.type === "capacity" ? "👥" : toast.type === "network" ? "🔌" : "⚙"}
      </div>
      <div className="toast-body">
        <p className="toast-title">
          {toast.type === "rateLimit" ? t(lang, "errorRateLimit")
            : toast.type === "capacity" ? t(lang, "errorCapacity")
            : toast.type === "network" ? t(lang, "errorNetwork")
            : t(lang, "errorServer")}
        </p>
        <p className="toast-detail">{toast.message}</p>
      </div>
    </div>
  );

  if (view === "title") {
    return <>{toastOverlay}<TitleScreen onStart={handleStart} onBuild={() => setView("builder")} onLoad={handleLoad} /></>;
  }

  if (view === "builder") {
    return <>{toastOverlay}<ThemeBuilder lang={lang} onComplete={() => setView("title")} onBack={() => setView("title")} /></>;
  }

  if (view === "loading") {
    return (
      <>{toastOverlay}
        <div className="loading-screen">
          <div className="loading-content">
            <div className="loading-orb">
              <div className="loading-orb-inner" />
            </div>
            <p className="loading-message">{loadingMessage}</p>
            <div className="loading-bar-bg">
              <div className="loading-bar-fill" />
            </div>
          </div>
        </div>
      </>
    );
  }

  if (view === "intro") {
    return (
      <>{toastOverlay}
        <div className="intro-screen">
          <div className="intro-overlay" />
          <div className="intro-content">
            <p className="intro-label">{t(lang, "introLabel")}</p>
            <h1 className="intro-title">{introTitle}</h1>
            <div className="intro-divider" />
            <p className="intro-description">{introDescription}</p>
            <div className="intro-prompt-box">
              <p className="intro-prompt-label">{t(lang, "introSituation")}</p>
              <p className="intro-prompt">{introPrompt}</p>
            </div>
            <button className="intro-start-btn" onClick={() => setView("story")}>
              {t(lang, "introBegin")}
            </button>
          </div>
        </div>
      </>
    );
  }

  return (
    <>{toastOverlay}
    <div className={`game-layout ${atmosphereClass}`}>
      {showMap && (
        <WorldMap
          lang={lang}
          stages={mapStages}
          loading={loading}
          onTravel={handleTravel}
          onClose={() => setShowMap(false)}
        />
      )}
      <main className="game-main">
        {view === "story" && (
          <StoryView lang={lang} scene={scene} choices={choices} loading={loading} onChoice={handleChoice}
            endingAvailable={endingAvailable} onEnding={handleEnding} onOpenMap={() => setShowMap(true)} />
        )}
        {view === "combat" && (
          <CombatView
            lang={lang} enemyName={enemyName} enemyDescription={enemyDesc}
            playerHp={playerHp} playerMaxHp={playerMaxHp}
            enemyHp={enemyHp} enemyMaxHp={enemyMaxHp}
            availableItems={combatItems} combatLog={combatLog}
            combatResult={combatResult} loading={loading}
            onAction={handleCombatAction} onContinue={handleCombatContinue}
          />
        )}
        {view === "ending" && endingData && (
          <EndingView lang={lang} ending={endingData} onReturn={handleEndingReturn} />
        )}
        {view === "gameover" && gameOverData && (
          <GameOverView
            lang={lang}
            data={gameOverData}
            onReturn={handleEndingReturn}
            onLoadSave={() => {
              // 파일 선택 트리거
              const input = document.createElement("input");
              input.type = "file";
              input.accept = ".json";
              input.onchange = (e) => {
                const file = (e.target as HTMLInputElement).files?.[0];
                if (!file) return;
                const reader = new FileReader();
                reader.onload = () => {
                  try {
                    const data = JSON.parse(reader.result as string);
                    handleLoad(data);
                  } catch { /* ignore */ }
                };
                reader.readAsText(file);
              };
              input.click();
            }}
          />
        )}
        {view === "dialogue" && (
          <DialogueView
            lang={lang} npcName={dialogueNpc} npcRole={dialogueRole}
            dispositionLabel={dialogueDisposition} messages={dialogueMessages}
            loading={loading} onSend={handleDialogueSend}
            onLeave={() => setView("story")}
          />
        )}
      </main>
      <aside className="game-sidebar">
        <Sidebar lang={lang} worldState={worldState} npcs={npcs} sceneCount={sceneCount} quests={quests} titles={titles} sessionId={sessionId} />
      </aside>
    </div>
    </>
  );
}
