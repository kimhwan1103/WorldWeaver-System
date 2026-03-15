// ── 월드 스테이트 ──

export interface WorldState {
  gauges: Record<string, number>;
  entities: Record<string, string>;
  properties: Record<string, string>;
  collections: Record<string, string[]>;
  gauge_labels: Record<string, string>;
}

// ── 씬 ──

export interface Choice {
  text: string;
  edge_feature: string;
  next_node_prompt: string;
  choice_type: "story" | "dialogue" | "combat";
  npc_name?: string;
  enemy_name?: string;
}

export interface SceneFeatures {
  mood: string;
  morality_impact: string;
}

export interface Scene {
  title: string;
  description: string;
  features: SceneFeatures;
  choices: Choice[];
  state_change: Record<string, unknown>;
}

export interface NPCInfo {
  name: string;
  role: string;
  disposition: string;
}

export interface SceneResponse {
  scene: Scene;
  choices: Choice[];
  world_state: WorldState;
  npcs: NPCInfo[];
  scene_count: number;
  redirect?: "dialogue" | "combat";
  npc_name?: string;
  enemy_name?: string;
}

// ── NPC 대화 ──

export interface NPCAction {
  type: "give_item" | "give_quest" | "reveal_info" | "refuse" | "attack";
  item?: string;
  quest?: string;
  info?: string;
}

export interface DialogueResponse {
  response: string;
  disposition: number;
  disposition_label: string;
  disposition_changed: boolean;
  action: NPCAction | null;
  should_end: boolean;
  world_state: WorldState;
}

// ── 전투 ──

export interface CombatEntity {
  name: string;
  description?: string;
  hp: number;
  max_hp: number;
  attack?: number;
  defense?: number;
}

export interface CombatStartResponse {
  enemy: CombatEntity;
  player: CombatEntity;
  available_items: string[];
}

export interface CombatActionDetail {
  type: string;
  detail: string;
  damage: number;
  success?: boolean;
}

export interface CombatResult {
  outcome: "victory" | "defeat" | "flee";
  rounds: number;
  damage_dealt: number;
  damage_taken: number;
  loot: string[];
  world_state: WorldState;
}

export interface CombatActionResponse {
  round: number;
  player_action: CombatActionDetail;
  enemy_action: CombatActionDetail;
  player_hp: number;
  player_max_hp: number;
  enemy_hp: number;
  enemy_max_hp: number;
  combat_over: boolean;
  result?: CombatResult;
}

// ── 테마 ──

export interface ThemeInfo {
  name: string;
  display_name: string;
  description: string;
  npc_count: number;
  enemy_count: number;
}

// ── 게임 세션 ──

export interface GameStartResponse {
  session_id: string;
  theme: string;
  initial_prompt: string;
  world_state: WorldState;
  enemies: string[];
}

// ── 게임 뷰 상태 ──

export type GameView = "title" | "story" | "combat" | "dialogue";
