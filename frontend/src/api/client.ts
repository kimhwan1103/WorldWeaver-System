const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

// 전역 에러 이벤트 (App에서 구독)
type ErrorListener = (error: { type: string; message: string }) => void;
const errorListeners: ErrorListener[] = [];
export function onApiError(listener: ErrorListener) {
  errorListeners.push(listener);
  return () => {
    const idx = errorListeners.indexOf(listener);
    if (idx >= 0) errorListeners.splice(idx, 1);
  };
}
function emitError(type: string, message: string) {
  errorListeners.forEach((fn) => fn({ type, message }));
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    emitError("network", "서버에 연결할 수 없습니다");
    throw new Error("서버에 연결할 수 없습니다");
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail: string = err.detail || "API 오류";

    // Rate limit / 할당량 초과 감지
    if (res.status === 429 || detail.includes("rate") || detail.includes("quota") || detail.includes("limit")) {
      emitError("rateLimit", detail);
    } else if (res.status === 503) {
      emitError("capacity", detail);
    } else if (res.status >= 500) {
      emitError("server", detail);
    }

    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  // 테마
  getThemes: () => request<{ themes: import("./types").ThemeInfo[] }>("/api/themes"),

  // 언어
  getLanguages: () =>
    request<{ languages: { code: string; label: string }[]; default: string }>("/api/languages"),

  // 게임 세션
  startGame: (theme: string, language: string = "ko") =>
    request<import("./types").GameStartResponse>("/api/game/start", {
      method: "POST",
      body: JSON.stringify({ theme, language }),
    }),

  generateScene: (sessionId: string, choiceIndex: number) =>
    request<import("./types").SceneResponse>("/api/game/scene", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, choice_index: choiceIndex }),
    }),

  getState: (sessionId: string) =>
    request<{ world_state: import("./types").WorldState }>(`/api/game/${sessionId}/state`),

  // NPC 대화
  dialogue: (sessionId: string, npcName: string, message: string) =>
    request<import("./types").DialogueResponse>("/api/dialogue", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, npc_name: npcName, message }),
    }),

  getNpcInfo: (sessionId: string, npcName: string) =>
    request<{ name: string; role: string; disposition: number; disposition_label: string }>(
      `/api/dialogue/${sessionId}/${npcName}/info`
    ),

  // 전투
  startCombat: (sessionId: string, enemyName: string) =>
    request<import("./types").CombatStartResponse>("/api/combat/begin", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, enemy_name: enemyName }),
    }),

  combatAction: (sessionId: string, action: string, itemName = "") =>
    request<import("./types").CombatActionResponse>("/api/combat/action", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, action, item_name: itemName }),
    }),

  // 게임오버
  generateGameOver: (sessionId: string) =>
    request<import("./types").GameOverResponse>(`/api/game/${sessionId}/gameover`, {
      method: "POST",
    }),

  // 세이브/로드
  saveGame: (sessionId: string) =>
    request<Record<string, unknown>>(`/api/game/${sessionId}/save`),

  loadGame: (saveData: Record<string, unknown>) =>
    request<{
      session_id: string;
      meta: Record<string, string>;
      scene_count: number;
      world_state: import("./types").WorldState;
      choices: import("./types").Choice[];
      npcs: import("./types").NPCInfo[];
      quests: import("./types").Quest[];
      titles: import("./types").Title[];
      map: import("./types").MapData;
      ending_available: boolean;
      last_scene?: import("./types").SceneResponse;
    }>("/api/game/load", {
      method: "POST",
      body: JSON.stringify({ save_data: saveData }),
    }),

  // 월드맵
  getMap: (sessionId: string) =>
    request<import("./types").MapData>(`/api/game/${sessionId}/map`),

  travel: (sessionId: string, stageName: string) =>
    request<import("./types").SceneResponse>("/api/game/travel", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, stage_name: stageName }),
    }),

  // 아이템/칭호
  getItemInfo: (sessionId: string, itemName: string) =>
    request<import("./types").ItemInfo>(`/api/game/${sessionId}/item/${encodeURIComponent(itemName)}`),

  investigateItem: (sessionId: string, itemName: string) =>
    request<import("./types").InvestigateResult>("/api/game/item/investigate", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, item_name: itemName }),
    }),

  getTitles: (sessionId: string) =>
    request<{ titles: import("./types").Title[] }>(`/api/game/${sessionId}/titles`),

  // 퀘스트
  getQuests: (sessionId: string) =>
    request<{ quests: import("./types").Quest[] }>(`/api/game/${sessionId}/quests`),

  completeQuest: (sessionId: string, npcName: string, questId: string) =>
    request<{ status: string; quests: import("./types").Quest[] }>("/api/game/quest/complete", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, npc_name: npcName, quest_id: questId }),
    }),

  // 엔딩
  checkEnding: (sessionId: string) =>
    request<{ available: boolean; ending: unknown }>(`/api/game/${sessionId}/ending/check`),

  generateEnding: (sessionId: string) =>
    request<import("./types").EndingResponse>(`/api/game/${sessionId}/ending`, {
      method: "POST",
    }),
};
