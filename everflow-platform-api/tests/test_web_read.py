"""Unit tests for knowledge web-read extraction (no network)."""

from app.services.web_read import (
    WebReadError,
    html_to_reader_markdown,
    is_thin_markdown,
    validate_public_http_url,
)


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


def test_validate_blocks_metadata_and_link_local() -> None:
    for url in (
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/",
        "http://[::ffff:169.254.169.254]/",
    ):
        try:
            validate_public_http_url(url)
            raise AssertionError(f"expected block for {url}")
        except WebReadError:
            pass


def test_validate_allows_public_https() -> None:
    try:
        assert validate_public_http_url("https://example.com/news/article") == (
            "https://example.com/news/article"
        )
    except WebReadError as exc:
        if "Unable to resolve" in str(exc):
            return
        raise


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


def test_is_thin_markdown_short() -> None:
    assert is_thin_markdown("short")
    assert is_thin_markdown("")
    long_ok = "x" * 500
    assert not is_thin_markdown(long_ok)


def test_is_thin_markdown_soft_block() -> None:
    body = (
        "Please enable JavaScript to continue. " + ("padding text here. " * 40)
    )
    assert is_thin_markdown(body)


def test_payload_method_defaults_on_http_shape() -> None:
    # fetch_reader_content is network-bound; just ensure helpers compose
    title, md = html_to_reader_markdown(
        "<html><head><title>T</title></head><body><article><p>"
        + ("word " * 200)
        + "</p></article></body></html>"
    )
    assert title == "T"
    assert not is_thin_markdown(md)
