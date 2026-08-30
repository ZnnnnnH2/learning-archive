from __future__ import annotations

import argparse
import json
from pathlib import Path

from .framework import freeze_framework
from .server import serve
from .service import TournamentService


def main() -> None:
    parser = argparse.ArgumentParser(description="Gomoku final-review tournament console")
    parser.add_argument("--data-dir", type=Path, default=Path("event-data"))
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init"); init.add_argument("--framework-root", type=Path, required=True)
    roster = sub.add_parser("import-roster"); roster.add_argument("csv", type=Path)
    submissions = sub.add_parser("import-submissions"); submissions.add_argument("directory", type=Path)
    sub.add_parser("import-github")
    preflight = sub.add_parser("preflight"); preflight.add_argument("--image", default="gcc:13")
    draw = sub.add_parser("draw"); draw.add_argument("--seed", type=int, required=True)
    run = sub.add_parser("run-game"); run.add_argument("game_id", type=int); run.add_argument("--image", default="gcc:13")
    sub.add_parser("advance-knockout")
    replay = sub.add_parser("replay"); replay.add_argument("game_id", type=int)
    web = sub.add_parser("serve"); web.add_argument("--host", default="127.0.0.1"); web.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(); args.data_dir.mkdir(parents=True, exist_ok=True)
    if args.command == "init":
        print(json.dumps(freeze_framework(args.framework_root, args.data_dir), ensure_ascii=False, indent=2)); return
    service = TournamentService(args.data_dir)
    try:
        if args.command == "import-roster": print(f"imported {service.import_roster(args.csv)} roster rows")
        elif args.command == "import-submissions": print(json.dumps(service.import_submissions(args.directory), ensure_ascii=False))
        elif args.command == "import-github": print(json.dumps(service.import_github(), ensure_ascii=False))
        elif args.command == "preflight": print(json.dumps(service.preflight(args.image), ensure_ascii=False))
        elif args.command == "draw": print(json.dumps(service.draw(args.seed), ensure_ascii=False, indent=2))
        elif args.command == "run-game": print(service.run_game(args.game_id, args.image))
        elif args.command == "advance-knockout": print(service.advance_knockout())
        elif args.command == "replay": print(json.dumps(service.replay(args.game_id), ensure_ascii=False, indent=2))
        elif args.command == "serve": serve(service, args.host, args.port)
    finally:
        if args.command != "serve": service.close()


if __name__ == "__main__":
    main()
