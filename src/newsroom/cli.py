"""Command-line entry point for the newsroom."""

import sys

from dotenv import load_dotenv

from newsroom import orchestrator


def main() -> None:
    load_dotenv()
    print("Multi-Agent Newsroom is ready.")
    print()
    try:
        path = orchestrator.run_pipeline()
        print(f"\nBriefing written to {path}")
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
