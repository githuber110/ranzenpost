from .upstream import file_response, read_endpoint


def register_routes(app, service):
    @app.get("/api/news/file")
    def news_file(connection: str = "", item: str = "", kind: str = "", index: int = -1, section: str = ""):
        return file_response(lambda: service.news_file(connection, item, kind, index, section), "news file")

    @app.get("/api/news/section")
    def news_section(section: str = ""):
        return read_endpoint(lambda: service.news_section(section))

    @app.get("/api/news/section/detail")
    def news_section_detail(connection: str = "", section: str = "", item: str = ""):
        return read_endpoint(lambda: service.news_section_detail(connection, section, item))
