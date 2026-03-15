import argparse
from pathlib import Path

from dotenv import load_dotenv


def cmd_build_theme(args):
    """세계관 문서를 분석하여 테마 JSON을 자동 생성."""
    from worldweaver.theme_builder import build_theme_from_lore, save_theme

    lore_dir = Path(args.lore_dir)
    if not lore_dir.exists():
        print(f"오류: '{lore_dir}' 폴더가 존재하지 않습니다.")
        return

    theme_data = build_theme_from_lore(lore_dir, theme_name=args.theme_name)
    output_path = save_theme(theme_data)

    print(f"\n완료! 다음 명령으로 게임을 시작할 수 있습니다:")
    print(f"  python main.py --theme {theme_data['name']} --mode interactive")


def cmd_play(args):
    """테마를 로드하고 게임을 실행."""
    from worldweaver.chain import build_story_chain
    from worldweaver.game import GameSession
    from worldweaver.graph import StoryGraph
    from worldweaver.prompt_loader import load_theme
    from worldweaver.rag import LoreMemory

    theme = load_theme(args.theme)
    print(f"테마 로드: {theme['display_name']}")

    lore_dir = Path(theme.get("lore_dir", "lore_documents"))

    memory = LoreMemory(lore_dir)
    chain = build_story_chain()
    graph = StoryGraph()
    session = GameSession(memory, chain, graph, theme)

    initial_prompt = theme["initial_prompt"]

    if args.mode == "interactive":
        session.run_interactive(initial_prompt)
    else:
        session.run_auto(initial_prompt, persona=args.persona, max_scenes=args.scenes)


def main():
    load_dotenv()

    from worldweaver.config import MAX_SCENES
    from worldweaver.prompt_loader import list_themes

    parser = argparse.ArgumentParser(description="WorldWeaver System - AI 기반 범용 스토리 생성 엔진")
    subparsers = parser.add_subparsers(dest="command")

    # ── build-theme 서브커맨드 ──
    build_parser = subparsers.add_parser(
        "build-theme",
        help="세계관 문서를 분석하여 테마 JSON을 자동 생성",
    )
    build_parser.add_argument(
        "--lore-dir",
        required=True,
        help="세계관 문서가 들어있는 폴더 경로",
    )
    build_parser.add_argument(
        "--theme-name",
        default=None,
        help="생성할 테마의 이름 (미지정 시 LLM이 자동 결정)",
    )

    # ── play 서브커맨드 ──
    available_themes = list_themes()
    play_parser = subparsers.add_parser(
        "play",
        help="테마를 로드하고 게임을 실행",
    )
    play_parser.add_argument(
        "--theme",
        choices=available_themes if available_themes else None,
        default="mythology",
        help=f"사용할 테마 (사용 가능: {', '.join(available_themes)})",
    )
    play_parser.add_argument(
        "--mode",
        choices=["interactive", "auto"],
        default="interactive",
        help="게임 모드",
    )
    play_parser.add_argument(
        "--persona",
        default="hero",
        help="자동 모드에서 사용할 페르소나",
    )
    play_parser.add_argument(
        "--scenes",
        type=int,
        default=MAX_SCENES,
        help=f"자동 모드에서 생성할 최대 씬 수 (기본: {MAX_SCENES})",
    )

    args = parser.parse_args()

    if args.command == "build-theme":
        cmd_build_theme(args)
    elif args.command == "play":
        cmd_play(args)
    else:
        parser.print_help()
        print("\n사용 예시:")
        print("  python main.py build-theme --lore-dir lore_documents")
        print("  python main.py play --theme mythology --mode interactive")


if __name__ == "__main__":
    main()
