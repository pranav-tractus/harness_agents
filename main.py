"""CLI entry point for the Extraction Agent POC.

Usage:
    python main.py --text "Your unstructured text here"
    python main.py --file path/to/input.txt --schema SalesOrderExtractContractKeyDetails
    python main.py --schema SOExtractContractList < input.txt

Available schemas are auto-discovered from models.py.
"""

import argparse
import inspect
import json
import logging
import sys
from typing import Type

from pydantic import BaseModel

import models as _models_module
from db import init_db
from extractor import ExtractionEngine

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


def _discover_schemas() -> dict[str, Type[BaseModel]]:
    return {
        name: obj
        for name, obj in inspect.getmembers(_models_module, inspect.isclass)
        if issubclass(obj, BaseModel) and obj is not BaseModel
    }


def _build_parser(schema_names: list[str]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Extraction Agent on unstructured text.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--text", "-t", type=str, help="Inline input text.")
    group.add_argument("--file", "-f", type=str, help="Path to a text file.")
    parser.add_argument(
        "--schema",
        "-s",
        choices=schema_names,
        default=schema_names[0] if schema_names else None,
        help="Pydantic schema to extract into (default: first discovered schema).",
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
    return parser


def main() -> None:
    schemas = _discover_schemas()
    if not schemas:
        print("ERROR: No Pydantic schemas found in models.py", file=sys.stderr)
        sys.exit(1)

    parser = _build_parser(list(schemas.keys()))
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Resolve input text
    if args.text:
        input_text = args.text
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            input_text = fh.read()
    elif not sys.stdin.isatty():
        input_text = sys.stdin.read()
    else:
        parser.print_help()
        sys.exit(0)

    schema = schemas[args.schema]

    init_db()
    engine = ExtractionEngine(model_key=args.model)
    result = engine.run(input_text, schema)

    print("\n" + "=" * 60)
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
