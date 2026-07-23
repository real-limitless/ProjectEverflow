"""Unit tests for knowledge web-read extraction (no network)."""

from app.services.web_read import WebReadError, html_to_reader_markdown, validate_public_http_url


def test_validate_blocks_localhost() -> None:
    for url in (
        "http://localhost/foo",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://192.168.1.1/x",
        "file:///etc/passwd",
    ):
        try:
            validate_public_http_url(url)
            raise AssertionError(f"expected block for {url}")
        except WebReadError:
            pass


def test_validate_allows_public_https() -> None:
    assert validate_public_http_url("https://example.com/news/article") == (
        "https://example.com/news/article"
    )


def test_html_extracts_article_body() -> None:
    html = """
    <html><head><title>Breaking News</title></head>
    <body>
      <nav>Home Ads</nav>
      <article>
        <h1>City opens new park</h1>
        <p>Officials cut the ribbon today.</p>
        <p>More details <a href="/more">here</a>.</p>
      </article>
      <footer>Copyright</footer>
    </body></html>
    """
    title, md = html_to_reader_markdown(html, base_url="https://news.example.com/a")
    assert title == "Breaking News"
    assert "City opens new park" in md
    assert "Officials cut the ribbon" in md
    assert "Copyright" not in md
    assert "Home Ads" not in md
    assert "https://news.example.com/more" in md
