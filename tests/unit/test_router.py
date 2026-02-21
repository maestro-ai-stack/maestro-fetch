from maestro_fetch.core.router import detect_type


def test_dropbox_url():
    assert detect_type("https://www.dropbox.com/sh/abc/def/file.csv") == "cloud"

def test_gdrive_url():
    assert detect_type("https://drive.google.com/file/d/abc123/view") == "cloud"

def test_youtube_url():
    assert detect_type("https://www.youtube.com/watch?v=abc123") == "media"

def test_youtube_short_url():
    assert detect_type("https://youtu.be/abc123") == "media"

def test_pdf_url():
    assert detect_type("https://example.com/report.pdf") == "doc"

def test_excel_url():
    assert detect_type("https://example.com/data.xlsx") == "doc"

def test_csv_url():
    assert detect_type("https://example.com/data.csv") == "doc"

def test_html_url():
    assert detect_type("https://example.com/page") == "web"

def test_html_url_with_html_ext():
    assert detect_type("https://example.com/page.html") == "web"
