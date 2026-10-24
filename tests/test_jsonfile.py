from iman import jsonfile


def test_broken_or_missing_json_reads_as_none(tmp_path):
    f = tmp_path / "plan.json"
    assert jsonfile.load(f) is None
    f.write_text("", encoding="utf-8")  # lo que dejaba el fallo de «charmap» en Windows
    assert jsonfile.load(f) is None
    jsonfile.save(f, {"hook_title": "Quedan 25 días para Japón 🇯🇵"})
    assert jsonfile.load(f)["hook_title"].endswith("🇯🇵")
    assert not (tmp_path / "plan.json.tmp").exists()
