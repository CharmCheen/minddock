from app.core.config import Settings


def test_settings_loads_dotenv_from_current_working_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("IMAGE_OCR_PROVIDER", raising=False)

    (tmp_path / ".env").write_text("IMAGE_OCR_PROVIDER=rapidocr\n", encoding="utf-8")

    settings = Settings()

    assert settings.image_ocr_provider == "rapidocr"


def test_environment_variables_override_defaults(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IMAGE_OCR_PROVIDER", "rapidocr")

    settings = Settings()

    assert settings.image_ocr_provider == "rapidocr"
