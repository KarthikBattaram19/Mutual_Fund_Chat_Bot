import pytest

from ingestion.parser import GrowwHTMLParser, ParserError


def fields(parsed_page):
    return {fact.field: fact for fact in parsed_page.facts}


def test_parser_extracts_factual_pairs_from_tables_and_definition_lists() -> None:
    html = """
    <html>
      <head><title>HDFC Large Cap Fund - Direct Growth</title></head>
      <body>
        <h1>HDFC Large Cap Fund - Direct Growth</h1>
        <table>
          <tr><th>NAV</th><td>Rs 1,024.18</td></tr>
          <tr><th>Expense Ratio</th><td>0.88%</td></tr>
        </table>
        <dl>
          <dt>Fund Manager</dt><dd>John Doe</dd>
          <dt>Benchmark Index</dt><dd>NIFTY 100 TRI</dd>
        </dl>
      </body>
    </html>
    """

    parsed = GrowwHTMLParser().parse(html, source_url="https://groww.in/mutual-funds/example")
    parsed_fields = fields(parsed)

    assert parsed.ok
    assert parsed.source_url == "https://groww.in/mutual-funds/example"
    assert parsed.title == "HDFC Large Cap Fund - Direct Growth"
    assert parsed_fields["nav"].value == "Rs 1,024.18"
    assert parsed_fields["expense_ratio"].value == "0.88%"
    assert parsed_fields["fund_manager"].value == "John Doe"
    assert parsed_fields["benchmark"].value == "NIFTY 100 TRI"


def test_parser_extracts_card_like_label_value_blocks() -> None:
    html = """
    <html>
      <body>
        <section>
          <div><span>Min SIP</span><span>Rs 100</span></div>
          <div><span>Riskometer</span><span>Very High</span></div>
          <div><span>Fund Size</span><span>Rs 32,100 Cr</span></div>
        </section>
      </body>
    </html>
    """

    parsed = GrowwHTMLParser().parse(html)
    parsed_fields = fields(parsed)

    assert parsed_fields["min_sip"].value == "Rs 100"
    assert parsed_fields["riskometer"].value == "Very High"
    assert parsed_fields["aum"].value == "Rs 32,100 Cr"


def test_parser_extracts_factual_fields_from_embedded_json() -> None:
    html = """
    <html>
      <body>
        <script id="__NEXT_DATA__" type="application/json">
          {
            "props": {
              "pageProps": {
                "scheme": {
                  "exitLoad": "1% if redeemed within 1 year",
                  "lockInPeriod": "No lock-in",
                  "category": "Large Cap"
                }
              }
            }
          }
        </script>
        <p>Editorial review text should not be treated as a fact.</p>
      </body>
    </html>
    """

    parsed = GrowwHTMLParser().parse(html)
    parsed_fields = fields(parsed)

    assert parsed_fields["exit_load"].source == "json"
    assert parsed_fields["exit_load"].value == "1% if redeemed within 1 year"
    assert parsed_fields["lock_in"].value == "No lock-in"
    assert parsed_fields["category"].value == "Large Cap"


def test_parser_uses_text_fallback_for_colon_separated_facts() -> None:
    html = """
    <html>
      <body>
        <main>
          NAV: Rs 500.10 | Expense Ratio: 0.72%; Exit Load: Nil
        </main>
      </body>
    </html>
    """

    parsed = GrowwHTMLParser().parse(html)
    parsed_fields = fields(parsed)

    assert parsed_fields["nav"].source == "text"
    assert parsed_fields["nav"].value == "Rs 500.10"
    assert parsed_fields["expense_ratio"].value == "0.72%"
    assert parsed_fields["exit_load"].value == "Nil"


def test_parser_dedupes_same_field_value_from_multiple_sources() -> None:
    html = """
    <html>
      <body>
        <script type="application/json">{"nav": "Rs 100.00"}</script>
        <table><tr><th>NAV</th><td>Rs 100.00</td></tr></table>
      </body>
    </html>
    """

    parsed = GrowwHTMLParser().parse(html)

    assert [fact.field for fact in parsed.facts].count("nav") == 1


def test_parser_excludes_editorial_review_and_performance_content() -> None:
    html = """
    <html>
      <body>
        <article>
          <h2>Should you invest in this fund?</h2>
          <p>This review compares returns and ratings.</p>
          <div><span>Returns</span><span>12%</span></div>
          <div><span>Expense Ratio</span><span>0.55%</span></div>
        </article>
      </body>
    </html>
    """

    parsed = GrowwHTMLParser().parse(html)

    assert [fact.field for fact in parsed.facts] == ["expense_ratio"]


def test_parser_flags_empty_or_unstructured_pages() -> None:
    parser = GrowwHTMLParser()

    empty = parser.parse("")
    unstructured = parser.parse("<html><body><p>No known facts here.</p></body></html>")

    assert empty.ok is False
    assert empty.warnings == ["HTML content is empty"]
    assert unstructured.ok is False
    assert unstructured.warnings == ["No structured factual fields found"]


def test_parser_can_raise_for_empty_html_in_strict_mode() -> None:
    with pytest.raises(ParserError, match="HTML content is empty"):
        GrowwHTMLParser().parse("", strict=True)
