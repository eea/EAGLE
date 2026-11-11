"""Examples are the .txt / .md files of a folder."""

from eagle_eye.examples import DEFAULT_DIR, load_examples


def test_labels_are_file_names_sorted(tmp_path):
    (tmp_path / "b second.txt").write_text("Two", encoding="utf-8")
    (tmp_path / "A first.md").write_text("# One", encoding="utf-8")
    assert list(load_examples(tmp_path)) == ["A first", "b second"]


def test_other_files_empty_files_and_hidden_files_are_skipped(tmp_path):
    for name, text in {"x.csv": "a", "readme.md": "doc", "README.TXT": "doc", ".hidden.txt": "a", "_old.txt": "a", "empty.txt": "  \n", "ok.TXT": "fine"}.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    (tmp_path / "folder.txt").mkdir()
    assert load_examples(tmp_path) == {"ok": "fine"}


def test_text_is_read_in_the_usual_encodings(tmp_path):
    (tmp_path / "utf8.txt").write_bytes("Wiese \u2013 gr\u00fcn\r\nzweite Zeile".encode("utf-8-sig"))
    (tmp_path / "cp1252.txt").write_bytes("Gr\u00fcnland".encode("cp1252"))
    loaded = load_examples(tmp_path)
    assert loaded["utf8"] == "Wiese \u2013 gr\u00fcn\nzweite Zeile"
    assert loaded["cp1252"] == "Gr\u00fcnland"


def test_same_name_with_two_extensions_keeps_both(tmp_path):
    (tmp_path / "a.md").write_text("one", encoding="utf-8")
    (tmp_path / "a.txt").write_text("two", encoding="utf-8")
    assert sorted(load_examples(tmp_path)) == ["a", "a.txt"]


def test_missing_folder_gives_no_examples(tmp_path):
    assert load_examples(tmp_path / "nope") == {}


def test_the_shipped_folder_has_examples():
    shipped = load_examples(DEFAULT_DIR)
    assert shipped and all(text.strip() for text in shipped.values())
