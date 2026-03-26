"""백엔드 다국어 텍스트 모듈.

게임 플레이 중 유저에게 보이는 모든 텍스트를 한/영/일 3개 언어로 제공한다.
"""

_TEXTS: dict[str, dict[str, str]] = {
    # ── 전투 진입/결과 ──
    "combat_title": {
        "ko": "전투: {name}",
        "en": "Combat: {name}",
        "ja": "戦闘: {name}",
    },
    "combat_desc": {
        "ko": "{name}과(와)의 전투가 시작되었다. {desc}",
        "en": "Combat with {name} has begun. {desc}",
        "ja": "{name}との戦闘が始まった。{desc}",
    },
    "combat_enter": {
        "ko": "전투 돌입",
        "en": "Enter combat",
        "ja": "戦闘突入",
    },
    "story_progress": {
        "ko": "이야기 진행",
        "en": "Story progress",
        "ja": "物語の進行",
    },

    # ── 전투 선택지 ──
    "combat_choice": {
        "ko": "⚔ {name}과(와) 전투",
        "en": "⚔ Fight {name}",
        "ja": "⚔ {name}と戦闘",
    },
    "npc_talk": {
        "ko": "💬 {name}({role})과(와) 대화하기",
        "en": "💬 Talk to {name} ({role})",
        "ja": "💬 {name}（{role}）と話す",
    },

    # ── 엔티티 상태 ──
    "entity_defeated": {
        "ko": "처치됨",
        "en": "Defeated",
        "ja": "討伐済み",
    },
    "entity_hostile": {
        "ko": "적대",
        "en": "Hostile",
        "ja": "敵対",
    },

    # ── 플레이어 ──
    "player_name": {
        "ko": "수호자",
        "en": "Guardian",
        "ja": "守護者",
    },

    # ── 전투 결과 요약 (그래프용) ──
    "result_victory": {
        "ko": "승리",
        "en": "Victory",
        "ja": "勝利",
    },
    "result_defeat": {
        "ko": "패배",
        "en": "Defeat",
        "ja": "敗北",
    },
    "result_flee": {
        "ko": "도주",
        "en": "Fled",
        "ja": "逃走",
    },
    "combat_summary": {
        "ko": "[전투: {name}] 결과: {outcome} | 총 {rounds}라운드 | 가한 피해: {dealt} | 받은 피해: {taken}",
        "en": "[Combat: {name}] Result: {outcome} | {rounds} rounds | Damage dealt: {dealt} | Damage taken: {taken}",
        "ja": "[戦闘: {name}] 結果: {outcome} | 全{rounds}ラウンド | 与ダメージ: {dealt} | 被ダメージ: {taken}",
    },
    "combat_loot": {
        "ko": "획득: {items}",
        "en": "Loot: {items}",
        "ja": "獲得: {items}",
    },
    "round_summary": {
        "ko": "라운드 {n}: 플레이어({p_type}) → {p_detail} | 적({e_type}) → {e_detail} | HP: {p_hp}/{p_max} vs {e_hp}/{e_max}",
        "en": "Round {n}: Player({p_type}) → {p_detail} | Enemy({e_type}) → {e_detail} | HP: {p_hp}/{p_max} vs {e_hp}/{e_max}",
        "ja": "ラウンド {n}: プレイヤー({p_type}) → {p_detail} | 敵({e_type}) → {e_detail} | HP: {p_hp}/{p_max} vs {e_hp}/{e_max}",
    },
    "combat_round_title": {
        "ko": "전투 라운드 {n}",
        "en": "Combat Round {n}",
        "ja": "戦闘ラウンド {n}",
    },
    "combat_round_edge": {
        "ko": "라운드 {n}",
        "en": "Round {n}",
        "ja": "ラウンド {n}",
    },
    "combat_result_title": {
        "ko": "전투 결과: {outcome}",
        "en": "Combat Result: {outcome}",
        "ja": "戦闘結果: {outcome}",
    },
    "combat_end": {
        "ko": "전투 종료",
        "en": "Combat end",
        "ja": "戦闘終了",
    },

    # ── 그래프 ──
    "start_node": {
        "ko": "시작",
        "en": "Start",
        "ja": "開始",
    },

    # ── 게임오버 원인 ──
    "gameover_health": {
        "ko": "체력이 완전히 소진되었다",
        "en": "Health has been completely exhausted",
        "ja": "体力が完全に尽きた",
    },
    "gameover_combat": {
        "ko": "연속 전투 패배로 더 이상 싸울 수 없다",
        "en": "Too many consecutive combat defeats to continue fighting",
        "ja": "連続戦闘敗北でこれ以上戦えない",
    },
    "gameover_allies": {
        "ko": "모든 동맹이 적대적으로 변했다",
        "en": "All allies have turned hostile",
        "ja": "すべての同盟が敵対的になった",
    },
    "gameover_quests": {
        "ko": "모든 퀘스트가 잊혀지고, 타락이 세계를 삼킨다",
        "en": "All quests have been forgotten, and corruption consumes the world",
        "ja": "すべてのクエストが忘れられ、堕落が世界を飲み込む",
    },
    "gameover_gauge": {
        "ko": "게임오버 조건 충족",
        "en": "Game over condition met",
        "ja": "ゲームオーバー条件達成",
    },
    "gameover_not_met": {
        "ko": "게임오버 조건 미충족",
        "en": "Game over condition not met",
        "ja": "ゲームオーバー条件未達成",
    },
    "gameover_gen_fail": {
        "ko": "게임오버 씬 생성 실패",
        "en": "Failed to generate game over scene",
        "ja": "ゲームオーバーシーン生成失敗",
    },
    "ending_not_met": {
        "ko": "엔딩 조건을 충족하지 않습니다",
        "en": "Ending conditions not met",
        "ja": "エンディング条件を満たしていません",
    },
    "ending_gen_fail": {
        "ko": "엔딩 생성 실패",
        "en": "Failed to generate ending",
        "ja": "エンディング生成失敗",
    },

    # ── 판정 (judgment) ──
    "judge_item_power": {
        "ko": "소지 중인 '{item}'의 힘이 작용한다",
        "en": "The power of '{item}' in your possession takes effect",
        "ja": "所持中の「{item}」の力が作用する",
    },
    "judge_item_hidden": {
        "ko": "'{item}'의 숨겨진 힘을 알고 있다",
        "en": "You know the hidden power of '{item}'",
        "ja": "「{item}」の隠された力を知っている",
    },
    "judge_quest_help": {
        "ko": "{name}에게 받은 임무의 맥락이 도움이 된다",
        "en": "The context of {name}'s quest helps you",
        "ja": "{name}から受けた任務の文脈が助けになる",
    },
    "judge_quest_lost": {
        "ko": "잊혀진 임무의 빈자리가 불안감을 준다",
        "en": "The void left by a forgotten quest brings unease",
        "ja": "忘れられた任務の空白が不安を与える",
    },
    "judge_combat_win": {
        "ko": "유사한 적과 싸워 승리한 경험이 있다",
        "en": "You have experience defeating a similar foe",
        "ja": "類似の敵と戦い勝利した経験がある",
    },
    "judge_combat_loss": {
        "ko": "이전 패배의 교훈이 떠오른다",
        "en": "Lessons from a previous defeat come to mind",
        "ja": "以前の敗北の教訓が思い浮かぶ",
    },
    "judge_health_low": {
        "ko": "체력이 위태롭다",
        "en": "Health is critically low",
        "ja": "体力が危険だ",
    },
    "judge_health_high": {
        "ko": "충분한 체력으로 자신감이 있다",
        "en": "With ample health, you feel confident",
        "ja": "十分な体力で自信がある",
    },
    "judge_corruption": {
        "ko": "타락의 기운이 판단력을 흐린다",
        "en": "The aura of corruption clouds your judgment",
        "ja": "堕落の気配が判断力を曇らせる",
    },
    "judge_seal": {
        "ko": "축적된 봉인력이 보호한다",
        "en": "Accumulated sealing power protects you",
        "ja": "蓄積された封印力が守る",
    },

    # ── 판정 결과 힌트 ──
    "judge_success_overwhelming": {
        "ko": "압도적 성공 — 기대 이상의 결과를 얻는다",
        "en": "Overwhelming success — results exceed all expectations",
        "ja": "圧倒的成功 — 期待以上の結果を得る",
    },
    "judge_success_clean": {
        "ko": "깔끔한 성공 — 의도한 대로 진행된다",
        "en": "Clean success — everything goes as planned",
        "ja": "鮮やかな成功 — 意図通りに進行する",
    },
    "judge_success_narrow": {
        "ko": "아슬아슬한 성공 — 간신히 해냈지만 대가가 따른다",
        "en": "Narrow success — barely made it, but at a cost",
        "ja": "ぎりぎりの成功 — 辛うじて成し遂げたが代償がある",
    },
    "judge_fail_minor": {
        "ko": "경미한 실패 — 상황이 약간 불리해진다",
        "en": "Minor failure — the situation becomes slightly unfavorable",
        "ja": "軽微な失敗 — 状況が少し不利になる",
    },
    "judge_fail_serious": {
        "ko": "심각한 실패 — 큰 대가를 치른다",
        "en": "Serious failure — a heavy price is paid",
        "ja": "深刻な失敗 — 大きな代償を払う",
    },
    "judge_fail_catastrophic": {
        "ko": "치명적 실패 — 상황이 급격히 악화된다",
        "en": "Catastrophic failure — the situation deteriorates rapidly",
        "ja": "致命的失敗 — 状況が急激に悪化する",
    },
    "judge_advantage": {
        "ko": "유리한 요소",
        "en": "Advantageous factors",
        "ja": "有利な要素",
    },
    "judge_disadvantage": {
        "ko": "불리한 요소",
        "en": "Disadvantageous factors",
        "ja": "不利な要素",
    },

    # ── 대화 ──
    "first_dialogue": {
        "ko": "(첫 대화)",
        "en": "(First conversation)",
        "ja": "(初対話)",
    },
    "npc_not_found": {
        "ko": "NPC '{name}' 또는 대화 체인 없음",
        "en": "NPC '{name}' or dialogue chain not found",
        "ja": "NPC「{name}」または対話チェーンが見つかりません",
    },
    "no_active_combat": {
        "ko": "활성 전투 없음",
        "en": "No active combat",
        "ja": "アクティブな戦闘がありません",
    },

    # ── 맵/스테이지 ──
    "stage_not_found": {
        "ko": "존재하지 않는 스테이지: {name}",
        "en": "Stage not found: {name}",
        "ja": "存在しないステージ: {name}",
    },
    "stage_locked": {
        "ko": "해금 조건을 충족하지 않습니다",
        "en": "Unlock conditions not met",
        "ja": "解放条件を満たしていません",
    },
    "stage_no_path": {
        "ko": "이 스테이지에서 직접 이동할 수 없습니다",
        "en": "Cannot travel directly from this stage",
        "ja": "このステージから直接移動できません",
    },

    # ── 서버 에러 ──
    "err_session_not_found": {
        "ko": "세션 없음",
        "en": "Session not found",
        "ja": "セッションが見つかりません",
    },
    "err_rate_limit": {
        "ko": "요청이 너무 많습니다. 잠시 후 다시 시도해주세요.",
        "en": "Too many requests. Please try again later.",
        "ja": "リクエストが多すぎます。しばらくしてからもう一度お試しください。",
    },
    "err_daily_limit": {
        "ko": "오늘의 AI 사용량을 초과했습니다. 내일 다시 시도해주세요.",
        "en": "Today's AI usage limit has been exceeded. Please try again tomorrow.",
        "ja": "本日のAI使用量を超えました。明日もう一度お試しください。",
    },
    "err_server": {
        "ko": "서버 내부 오류가 발생했습니다.",
        "en": "An internal server error occurred.",
        "ja": "サーバー内部エラーが発生しました。",
    },
    "err_start_failed": {
        "ko": "게임 시작에 실패했습니다. 잠시 후 다시 시도해주세요.",
        "en": "Failed to start game. Please try again later.",
        "ja": "ゲームの開始に失敗しました。しばらくしてからもう一度お試しください。",
    },
    "err_bad_choice": {
        "ko": "잘못된 선택지 인덱스",
        "en": "Invalid choice index",
        "ja": "無効な選択肢インデックス",
    },
    "err_bad_choice_ws": {
        "ko": "잘못된 선택지",
        "en": "Invalid choice",
        "ja": "無効な選択肢",
    },
    "err_ws_rate": {
        "ko": "요청이 너무 빠릅니다. 잠시 후 다시 시도해주세요.",
        "en": "Requests too fast. Please slow down.",
        "ja": "リクエストが速すぎます。少し待ってからお試しください。",
    },
    "err_theme_not_found": {
        "ko": "테마 '{name}' 없음",
        "en": "Theme '{name}' not found",
        "ja": "テーマ「{name}」が見つかりません",
    },
    "err_session_create": {
        "ko": "세션 생성 실패",
        "en": "Failed to create session",
        "ja": "セッション作成失敗",
    },
    "err_load_failed": {
        "ko": "로드 실패",
        "en": "Load failed",
        "ja": "ロード失敗",
    },
    "err_quest_fail": {
        "ko": "퀘스트 완료 실패",
        "en": "Quest completion failed",
        "ja": "クエスト完了失敗",
    },
    "no_hidden_effect": {
        "ko": "발견할 히든 효과가 없습니다",
        "en": "No hidden effects to discover",
        "ja": "発見する隠し効果はありません",
    },

    # ── 빌더 ──
    "builder_demo_blocked": {
        "ko": "데모 모드에서는 테마 빌더를 사용할 수 없습니다.",
        "en": "Theme builder is not available in demo mode.",
        "ja": "デモモードではテーマビルダーを使用できません。",
    },
    "builder_wrong_pw": {
        "ko": "비밀번호가 올바르지 않습니다",
        "en": "Incorrect password",
        "ja": "パスワードが正しくありません",
    },
    "builder_no_files": {
        "ko": "유효한 .txt 파일이 없습니다",
        "en": "No valid .txt files found",
        "ja": "有効な.txtファイルがありません",
    },
    "builder_not_found": {
        "ko": "빌드 작업 없음",
        "en": "Build job not found",
        "ja": "ビルドジョブが見つかりません",
    },
    "builder_building": {
        "ko": "테마 빌드 시작...",
        "en": "Starting theme build...",
        "ja": "テーマビルド開始...",
    },
    "builder_complete": {
        "ko": "테마 '{name}' 생성 완료!",
        "en": "Theme '{name}' created!",
        "ja": "テーマ「{name}」作成完了！",
    },
    "builder_error": {
        "ko": "테마 빌드 중 오류가 발생했습니다.",
        "en": "An error occurred during theme building.",
        "ja": "テーマビルド中にエラーが発生しました。",
    },
    "builder_error_detail": {
        "ko": "빌드 처리 중 문제가 발생했습니다. 다시 시도해주세요.",
        "en": "An issue occurred during build processing. Please try again.",
        "ja": "ビルド処理中に問題が発生しました。もう一度お試しください。",
    },

    # ── NPC デフォルト ──
    "default_personality": {
        "ko": "중립적인 성격",
        "en": "Neutral personality",
        "ja": "中立的な性格",
    },
    "default_tone": {
        "ko": "평범한 말투",
        "en": "Ordinary tone",
        "ja": "普通の話し方",
    },
    "default_role": {
        "ko": "일반",
        "en": "General",
        "ja": "一般",
    },

    # ── NPC 호감도 ──
    "npc_disposition": {
        "ko": "호감도: {label}",
        "en": "Disposition: {label}",
        "ja": "好感度: {label}",
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    """다국어 텍스트 조회. kwargs로 포맷팅 변수를 전달."""
    entry = _TEXTS.get(key)
    if not entry:
        return key
    text = entry.get(lang, entry.get("en", key))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text
