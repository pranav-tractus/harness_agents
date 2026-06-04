import argparse
import logging
import os
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def cmd_ingest(args: argparse.Namespace) -> None:
    from graph.kuzu_backend import KuzuBackend
    from graph.ingestion import ingest_all

    db_path = Path(os.environ.get("KUZU_DB_PATH", "graph.db"))
    if args.reset and db_path.exists():
        import shutil
        shutil.rmtree(db_path) if db_path.is_dir() else db_path.unlink()
        print(f"Cleared existing graph DB at {db_path}")

    backend = KuzuBackend(db_path=db_path)
    count = ingest_all(Path(args.data_dir), backend, model_key=args.model)
    backend.close()
    print(f"Ingested {count} episodes into {db_path}")


def cmd_qa(args: argparse.Namespace) -> None:
    from graph.client import GraphitiMemoryClient

    client = GraphitiMemoryClient()
    answer = client.answer_question(args.customer_id, args.question)
    print(answer)
    client.close()


def cmd_memory(args: argparse.Namespace) -> None:
    from graph.client import GraphitiMemoryClient

    client = GraphitiMemoryClient()
    block = client.get_memory_block(args.customer_id)
    if block:
        print(block)
    else:
        print(f"No history found for customer: {args.customer_id}")
    client.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m graph", description="Knowledge graph CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Ingest raw_data into the graph")
    p_ingest.add_argument("--data-dir", default="raw_data", help="Path to raw_data directory")
    p_ingest.add_argument("--model", default="claude-sonnet-4-6", help="Model key for extraction")
    p_ingest.add_argument("--reset", action="store_true", help="Clear the graph DB before ingesting")
    p_ingest.set_defaults(func=cmd_ingest)

    p_qa = sub.add_parser("qa", help="Ask a question about a customer")
    p_qa.add_argument("customer_id", help="Customer ID to query")
    p_qa.add_argument("question", help="Question to answer")
    p_qa.set_defaults(func=cmd_qa)

    p_mem = sub.add_parser("memory", help="Print memory block for a customer")
    p_mem.add_argument("customer_id", help="Customer ID to retrieve memory for")
    p_mem.set_defaults(func=cmd_memory)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
