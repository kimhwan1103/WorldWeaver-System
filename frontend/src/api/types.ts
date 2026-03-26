// ── 월드 스테이트 ──

export interface WorldState {
  gauges: Record<string, number>;
  entities: Record<string, string>;
  properties: Record<string, string>;
  collections: Record<string, string[]>;
  gauge_labels: Record<string, string>;
  property_labels?: Record<string, string>;
  collection_labels?: Record<string, string>;
}

// ── 씬 ──

export interface Choice {
  text: string;
  edge_feature: string;
  next_node_prompt: string;
  choice_type: "story" | "dialogue" | "combat";
  npc_name?: string;
  enemy_name?: string;
  risky?: boolean;
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
  quests?: Quest[];
  ending_available?: boolean;
  titles?: Title[];
  map?: MapData;
  game_over?: GameOverInfo;
  redirect?: "dialogue" | "combat";
  npc_name?: string;
  enemy_name?: string;
  greeting?: NPCGreeting;
}

export interface NPCGreeting {
  npc_name: string;
  npc_key?: string;    // 원본 이름 (API 호출용)
  role: string;
  greeting: string;
  disposition: number;
  disposition_label: string;
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
  quests?: Quest[];
  recovered_memories?: { type: string; content: string }[];
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
  game_over?: GameOverInfo;
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
  world_state?: WorldState;
  result?: CombatResult;
}

// ── 퀘스트 ──

export interface Quest {
  id: string;
  content: string;
  npc: string;         // 번역된 NPC 이름
  npc_key: string;     // 원본 NPC 이름 (API 호출용)
  status: "active" | "fading" | "lost" | "completed";
  stage: string;
  edge_count: number;
}

// ── 아이템/칭호 ──

export interface ItemInfo {
  name: string;
  description: string;
  base_effect: Record<string, number>;
  total_effect: Record<string, number>;
  is_consumable: boolean;
  hidden_discovered: boolean;
  has_hidden: boolean;
  hidden_effect?: Record<string, number>;
  origin_type: string;
  origin_name: string;
}

export interface Title {
  id: string;
  name: string;
  description: string;
  bonus: Record<string, number>;
}

export interface InvestigateResult {
  discovered: boolean;
  item?: string;
  hidden_effect?: Record<string, number>;
  description?: string;
  new_titles?: Title[];
  message?: string;
}

// ── 게임오버 ──

export interface GameOverInfo {
  game_over_id: string;
  cause: string;
  factors: Record<string, string>;
}

export interface GameOverResponse {
  game_over_id: string;
  cause: string;
  title: string;
  epilogue: string;
  final_line: string;
  tone: string;
  factors: Record<string, string>;
}

// ── ���딩 ──

export interface EndingResponse {
  ending_id: string;
  ending_type: string;
  title: string;
  epilogue: string;
  final_line: string;
  tone: string;
  conditions_met: Record<string, string>;
  world_state: WorldState;
  quests: Quest[];
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
  description: string;
  initial_prompt: string;
  world_state: WorldState;
  enemies: string[];
}

// ── 월드맵 ──

export interface StageInfo {
  name: string;
  display_name: string;
  description: string;
  layer: number;
  connects_to: string[];
  unlocked: boolean;
  visited: boolean;
  is_current: boolean;
  npcs: string[];
  enemies: string[];
  unlock_hint: string;
}

export interface MapData {
  current_stage: string;
  stages: StageInfo[];
}

// ── 게임 뷰 상태 ──

export type GameView = "title" | "builder" | "loading" | "intro" | "story" | "combat" | "dialogue" | "ending" | "map" | "gameover";
