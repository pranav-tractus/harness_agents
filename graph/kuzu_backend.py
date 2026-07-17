import logging
from pathlib import Path

import kuzu

logger = logging.getLogger(__name__)

_VALID_TABLES = frozenset({"Customer", "Product", "Port", "Episode"})
_VALID_PK_COLS = frozenset({"id", "name", "source_id"})

_DDL = [
    "CREATE NODE TABLE IF NOT EXISTS Customer(id STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE IF NOT EXISTS Product(name STRING, PRIMARY KEY(name))",
    "CREATE NODE TABLE IF NOT EXISTS Port(name STRING, PRIMARY KEY(name))",
    "CREATE NODE TABLE IF NOT EXISTS Episode(source_id STRING, customer_id STRING, timestamp INT64, PRIMARY KEY(source_id))",
    "CREATE REL TABLE IF NOT EXISTS BUYS(FROM Customer TO Product, quantity DOUBLE, unit STRING, price DOUBLE, price_unit STRING, incoterm STRING, timestamp INT64, source_id STRING)",
    "CREATE REL TABLE IF NOT EXISTS SHIPS_TO(FROM Customer TO Port, incoterm STRING, timestamp INT64, source_id STRING)",
    "CREATE REL TABLE IF NOT EXISTS HAS_TERMS(FROM Customer TO Episode, payment_terms STRING, packing STRING, loading STRING)",
]


class KuzuBackend:
    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            db_path = Path("graph.db")
        self._db = kuzu.Database(str(db_path))
        self._conn = kuzu.Connection(self._db)
        self._init_schema()

    def _init_schema(self) -> None:
        for ddl in _DDL:
            self._conn.execute(ddl)

    def _upsert_node(self, table: str, pk_col: str, pk_val: str) -> None:
        if table not in _VALID_TABLES or pk_col not in _VALID_PK_COLS:
            raise ValueError(f"Invalid table/column: {table!r}.{pk_col!r}")
        check = self._conn.execute(
            f"MATCH (n:{table} {{{pk_col}: $val}}) RETURN count(n) AS c",
            {"val": pk_val},
        )
        count = check.get_next()[0]
        if count == 0:
            self._conn.execute(
                f"CREATE (:{table} {{{pk_col}: $val}})",
                {"val": pk_val},
            )

    def write_episode(self, episode: dict) -> bool:
        """Write episode to the graph. Returns True if written, False if already exists."""
        source_id = episode["source_id"]
        customer_id = episode["customer_id"]
        timestamp = episode.get("timestamp", 0)
        entities = episode.get("entities", {})

        # Idempotency check
        existing = self._conn.execute(
            "MATCH (e:Episode {source_id: $sid}) RETURN count(e) AS c",
            {"sid": source_id},
        )
        if existing.get_next()[0] > 0:
            logger.debug("Episode already exists, skipping: %s", source_id)
            return False

        self._upsert_node("Customer", "id", customer_id)
        self._conn.execute(
            "CREATE (:Episode {source_id: $sid, customer_id: $cid, timestamp: $ts})",
            {"sid": source_id, "cid": customer_id, "ts": timestamp},
        )

        ports_written: set[str] = set()
        for product in entities.get("products", []):
            pname = product.get("name", "").strip()
            if not pname:
                continue
            self._upsert_node("Product", "name", pname)
            port = (product.get("port") or "").strip()
            if port:
                self._upsert_node("Port", "name", port)
            self._conn.execute(
                """
                MATCH (c:Customer {id: $cid}), (p:Product {name: $pname})
                CREATE (c)-[:BUYS {
                    quantity: $qty, unit: $unit, price: $price,
                    price_unit: $price_unit, incoterm: $inco,
                    timestamp: $ts, source_id: $sid
                }]->(p)
                """,
                {
                    "cid": customer_id,
                    "pname": pname,
                    "qty": float(product.get("quantity") or 0),
                    "unit": product.get("unit") or "",
                    "price": float(product.get("price") or 0),
                    "price_unit": product.get("price_unit") or "",
                    "inco": product.get("incoterm") or "",
                    "ts": timestamp,
                    "sid": source_id,
                },
            )
            if port:
                self._conn.execute(
                    """
                    MATCH (c:Customer {id: $cid}), (po:Port {name: $port})
                    CREATE (c)-[:SHIPS_TO {incoterm: $inco, timestamp: $ts, source_id: $sid}]->(po)
                    """,
                    {"cid": customer_id, "port": port,
                     "inco": product.get("incoterm") or "",
                     "ts": timestamp, "sid": source_id},
                )
                ports_written.add(port)

        for port in entities.get("ports", []):
            port = port.strip()
            if not port or port in ports_written:
                continue
            self._upsert_node("Port", "name", port)
            self._conn.execute(
                """
                MATCH (c:Customer {id: $cid}), (po:Port {name: $port})
                CREATE (c)-[:SHIPS_TO {incoterm: '', timestamp: $ts, source_id: $sid}]->(po)
                """,
                {"cid": customer_id, "port": port, "ts": timestamp, "sid": source_id},
            )
            ports_written.add(port)

        payment_terms = entities.get("payment_terms") or ""
        packing = entities.get("packing") or ""
        loading = entities.get("loading") or ""
        if any((payment_terms, packing, loading)):
            self._conn.execute(
                """
                MATCH (c:Customer {id: $cid}), (e:Episode {source_id: $sid})
                CREATE (c)-[:HAS_TERMS {
                    payment_terms: $pt, packing: $pk, loading: $ld
                }]->(e)
                """,
                {"cid": customer_id, "sid": source_id,
                 "pt": payment_terms, "pk": packing, "ld": loading},
            )

        return True

    def query_customer(self, customer_id: str) -> list[dict]:
        rows: list[dict] = []

        # Products
        res = self._conn.execute(
            """
            MATCH (c:Customer {id: $cid})-[b:BUYS]->(p:Product)
            RETURN p.name AS product_name, b.quantity AS quantity, b.unit AS unit,
                   b.price AS price, b.price_unit AS price_unit,
                   b.incoterm AS incoterm, b.timestamp AS timestamp, b.source_id AS source_id
            ORDER BY b.timestamp DESC
            """,
            {"cid": customer_id},
        )
        while res.has_next():
            row = res.get_next()
            rows.append({
                "type": "product",
                "product_name": row[0],
                "quantity": row[1],
                "unit": row[2],
                "price": row[3],
                "price_unit": row[4],
                "incoterm": row[5],
                "timestamp": row[6],
                "source_id": row[7],
            })

        # Ports
        res = self._conn.execute(
            """
            MATCH (c:Customer {id: $cid})-[s:SHIPS_TO]->(po:Port)
            RETURN po.name AS port, s.incoterm AS incoterm, s.timestamp AS ts, s.source_id AS sid
            ORDER BY s.timestamp DESC
            """,
            {"cid": customer_id},
        )
        while res.has_next():
            row = res.get_next()
            rows.append({
                "type": "port",
                "port": row[0],
                "incoterm": row[1],
                "timestamp": row[2],
                "source_id": row[3],
            })

        # Terms
        res = self._conn.execute(
            """
            MATCH (c:Customer {id: $cid})-[t:HAS_TERMS]->(e:Episode)
            RETURN t.payment_terms AS payment_terms, t.packing AS packing,
                   t.loading AS loading, e.timestamp AS ts, e.source_id AS sid
            ORDER BY e.timestamp DESC
            """,
            {"cid": customer_id},
        )
        while res.has_next():
            row = res.get_next()
            rows.append({
                "type": "terms",
                "payment_terms": row[0],
                "packing": row[1],
                "loading": row[2],
                "timestamp": row[3],
                "source_id": row[4],
            })

        return rows

    def close(self) -> None:
        pass  # kuzu connection has no explicit close in Python SDK
