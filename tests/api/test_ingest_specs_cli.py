from apps.api.services.spec_ingest_service import IngestReport
from scripts import ingest_specs


def _run(monkeypatch, reports, argv):
    seen = {}

    def _fake_folder(folder, **kwargs):
        seen["folder"] = str(folder)
        seen["kwargs"] = kwargs
        return reports

    monkeypatch.setattr(ingest_specs.spec_ingest_service, "ingest_folder", _fake_folder)
    code = ingest_specs.main(argv)
    return code, seen


def test_main_prints_table_and_returns_zero(monkeypatch, capsys):
    reports = [
        IngestReport(file="a.pdf", code="A-1", name="Alpha", status="ingested", aliases=2),
        IngestReport(file="b.pdf", code="B-1", name="Beta", status="skipped"),
    ]
    code, seen = _run(monkeypatch, reports, ["prod_specs"])
    out = capsys.readouterr().out
    assert code == 0
    assert seen["folder"] == "prod_specs"
    assert seen["kwargs"]["dry_run"] is False
    assert "a.pdf" in out and "A-1" in out and "ingested" in out
    assert "1 ingested" in out and "1 skipped" in out


def test_main_flags_are_forwarded(monkeypatch, capsys):
    code, seen = _run(monkeypatch, [], ["prod_specs", "--dry-run", "--force", "--model", "sonnet-4-6"])
    assert code == 0
    assert seen["kwargs"]["dry_run"] is True
    assert seen["kwargs"]["force"] is True
    assert seen["kwargs"]["model_key"] == "sonnet-4-6"


def test_main_returns_one_on_failure(monkeypatch, capsys):
    reports = [IngestReport(file="bad.pdf", status="failed", error="boom")]
    code, _ = _run(monkeypatch, reports, ["prod_specs"])
    out = capsys.readouterr().out
    assert code == 1
    assert "boom" in out
