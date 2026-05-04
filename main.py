"""CLI entry point for the Extraction Agent POC.

Schemas are locked:
- initial extraction always uses ``SOExtractContractList``
- summary updates always use ``SOUpdateContractList``

Usage:
    # initial extraction
    python main.py --text "Your unstructured text here"
    python main.py --file path/to/input.txt
    python main.py < input.txt

    # human-in-the-loop summary update
    python main.py --update --previous summary.json --instruction "Change KNM Coffee qty to 8 bags"
    python main.py --update --previous summary.json --instruction-file note.txt --file chat.txt

The CLI prints the result JSON; it does NOT persist anything to the database.
Use the Streamlit UI ("Save" button) to commit a summary to the ``summaries`` table.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from chat_loader import build_extraction_few_shot_from_paths
from extractor import ExtractionEngine
from prompt_builder import INITIAL_FEW_SHOT_DB_LIMIT_DEFAULT

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Extraction Agent on unstructured text.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Run summary update mode (requires --previous and --instruction/--instruction-file).",
    )

    src_group = parser.add_mutually_exclusive_group()
    src_group.add_argument("--text", "-t", type=str, help="Inline input text.")
    src_group.add_argument("--file", "-f", type=str, help="Path to a chat/text file.")

    parser.add_argument(
        "--previous",
        "-p",
        type=str,
        help="Path to a JSON file containing the previous summary (required for --update).",
    )
    instr_group = parser.add_mutually_exclusive_group()
    instr_group.add_argument(
        "--instruction",
        "-i",
        type=str,
        help="Update instruction text (required for --update unless --instruction-file is given).",
    )
    instr_group.add_argument(
        "--instruction-file",
        type=str,
        help="Path to a file containing the update instruction.",
    )

    parser.add_argument(
        "--model",
        "-m",
        default="default",
        help="Bedrock model key from BEDROCK_ANTHROPIC_MODELS (default: 'default').",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable DEBUG logging."
    )
    parser.add_argument(
        "--few-shot-file",
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "JSON chat file to use as an initial-extraction few-shot example (repeatable). "
            "Gold output is read from field_data or, for update scenarios, generated_summary. "
            "Paths are usually under raw_data/chats/, raw_data/downloaded_chats/, or "
            "raw_data/chats/updates/."
        ),
    )
    parser.add_argument(
        "--no-db-few-shot",
        action="store_true",
        help="Do not include few-shot examples from the database (only --few-shot-file, if any).",
    )
    return parser


def _read_input_text(args) -> str:
    if args.text:
        return args.text
    if args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            return fh.read()
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    engine = ExtractionEngine(model_key=args.model)

    if args.update:
        if not args.previous:
            parser.error("--update requires --previous <path-to-json>")
        instruction = args.instruction
        if args.instruction_file:
            with open(args.instruction_file, "r", encoding="utf-8") as fh:
                instruction = fh.read()
        if not instruction:
            parser.error("--update requires --instruction or --instruction-file")

        with open(args.previous, "r", encoding="utf-8") as fh:
            previous_summary = json.load(fh)

        original_input_text = _read_input_text(args) or None

        result = engine.update(
            previous_summary=previous_summary,
            update_instruction=instruction,
            original_input_text=original_input_text,
        )
    else:
        input_text = _read_input_text(args)
        if not input_text.strip():
            parser.print_help()
            sys.exit(0)
        extra_fs = build_extraction_few_shot_from_paths([Path(p) for p in args.few_shot_file])
        db_lim = 0 if args.no_db_few_shot else INITIAL_FEW_SHOT_DB_LIMIT_DEFAULT
        result = engine.run(
            input_text,
            extra_few_shot_examples=extra_fs or None,
            db_few_shot_limit=db_lim,
        )

    print("\n" + "=" * 60)
    print(f"Mode     : {'UPDATE' if args.update else 'INITIAL'}")
    print(f"Status   : {result.status.upper()}")
    print(f"Schema   : {result.schema_name}")
    print(f"Attempts : {result.attempts}")
    print("=" * 60)

    if result.status == "success" and result.output_json is not None:
        print(json.dumps(json.loads(result.output_json), indent=2))
    else:
        print(f"Error: {result.error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
