from dataclasses import dataclass, field

import numpy as np

from apps.api.settings import get_settings
from core.embeddings import DIMENSION


@dataclass
class VectorRecord:
    key: str
    embedding: list[float]
    metadata: dict = field(default_factory=dict)


@dataclass
class VectorHit:
    key: str
    score: float
    metadata: dict = field(default_factory=dict)


class InMemoryIndex:
    """Numpy cosine index for tests and offline dev."""

    def __init__(self):
        self._store: dict[str, VectorRecord] = {}

    def ensure(self, dimension: int = DIMENSION) -> None:
        pass

    def put(self, records: list[VectorRecord]) -> None:
        for r in records:
            self._store[r.key] = r

    def delete(self, keys: list[str]) -> None:
        for k in keys:
            self._store.pop(k, None)

    def query(self, embedding: list[float], top_k: int = 5) -> list[VectorHit]:
        q = np.asarray(embedding, dtype=np.float32)
        hits = []
        for r in self._store.values():
            v = np.asarray(r.embedding, dtype=np.float32)
            denom = float(np.linalg.norm(q) * np.linalg.norm(v))
            score = float(q @ v) / denom if denom else 0.0
            hits.append(VectorHit(key=r.key, score=score, metadata=dict(r.metadata)))
        return sorted(hits, key=lambda h: -h.score)[:top_k]


class S3VectorsIndex:
    def __init__(self, bucket: str, index: str, *, client=None):
        self._bucket = bucket
        self._index = index
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from core.utils import create_boto3_client

            self._client = create_boto3_client("s3vectors", region=get_settings().aws_region)
        return self._client

    def ensure(self, dimension: int = DIMENSION) -> None:
        try:
            self.client.get_index(vectorBucketName=self._bucket, indexName=self._index)
            return
        except self.client.exceptions.NotFoundException:
            pass
        try:
            self.client.create_vector_bucket(vectorBucketName=self._bucket)
        except self.client.exceptions.ConflictException:
            pass
        self.client.create_index(
            vectorBucketName=self._bucket,
            indexName=self._index,
            dataType="float32",
            dimension=dimension,
            distanceMetric="cosine",
            metadataConfiguration={"nonFilterableMetadataKeys": ["snippet"]},
        )

    def put(self, records: list[VectorRecord]) -> None:
        self.client.put_vectors(
            vectorBucketName=self._bucket,
            indexName=self._index,
            vectors=[
                {
                    "key": r.key,
                    "data": {"float32": [float(x) for x in r.embedding]},
                    "metadata": r.metadata,
                }
                for r in records
            ],
        )

    def delete(self, keys: list[str]) -> None:
        if not keys:
            return
        self.client.delete_vectors(
            vectorBucketName=self._bucket, indexName=self._index, keys=list(keys)
        )

    def query(self, embedding: list[float], top_k: int = 5) -> list[VectorHit]:
        resp = self.client.query_vectors(
            vectorBucketName=self._bucket,
            indexName=self._index,
            topK=top_k,
            queryVector={"float32": [float(x) for x in embedding]},
            returnMetadata=True,
            returnDistance=True,
        )
        return [
            VectorHit(
                key=v["key"],
                score=1.0 - float(v.get("distance") or 0.0),
                metadata=v.get("metadata") or {},
            )
            for v in resp.get("vectors", [])
        ]


def default_index() -> S3VectorsIndex:
    s = get_settings()
    return S3VectorsIndex(s.vector_bucket, s.vector_index)


def is_available() -> bool:
    return bool(get_settings().vector_bucket)
