from awescholar import pubmed


def test_record_parses_pubmed_xml(monkeypatch):
    xml = b"""
    <PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>42753698</PMID>
      <Article><ArticleTitle>An open benchmark and language models for AI in aging biology</ArticleTitle>
        <Abstract><AbstractText>Abstract text.</AbstractText></Abstract>
        <Journal><Title>Cell</Title><JournalIssue><PubDate><Year>2026</Year><Month>Aug</Month></PubDate></JournalIssue></Journal>
        <AuthorList><Author><ForeName>Jane</ForeName><LastName>Doe</LastName></Author></AuthorList>
        <ArticleDate><Year>2026</Year><Month>08</Month></ArticleDate>
        <PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
        <ELocationID EIdType="doi">10.1016/j.cell.2026.08.026</ELocationID>
      </Article></MedlineCitation></PubmedArticle></PubmedArticleSet>
    """
    monkeypatch.setattr(pubmed, "_request", lambda path, params: xml if path == "efetch.fcgi" else b'{"esearchresult":{"idlist":["42753698"]}}')
    records = pubmed.search_pubmed("aging biology", limit=1)
    assert records[0]["doi"] == "10.1016/j.cell.2026.08.026"
    assert records[0]["title"].startswith("An open benchmark")
    assert records[0]["authors"] == ["Jane Doe"]
    assert records[0]["url"].endswith("42753698/")
