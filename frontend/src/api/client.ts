const API_BASE = "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "API 오류");
  }
  return res.json();
}

export const api = {
  // 테마
  getThemes: () => request<{ themes: import("./types").ThemeInfo[] }>("/api/themes"),

  // 게임 세션
  startGame: (theme: string) =>
    request<import("./types").GameStartResponse>("/api/game/start", {
      method: "POST",
      body: JSON.stringify({ theme }),
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
};
