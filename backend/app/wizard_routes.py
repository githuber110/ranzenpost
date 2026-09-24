from fastapi import Body


def register_routes(app, wizard):
    @app.get("/api/wizard")
    def wizard_status():
        return wizard.status()

    @app.post("/api/wizard/url")
    def wizard_url(body: dict = Body(...)):
        return wizard.set_url(body.get("url", ""))

    @app.post("/api/wizard/login")
    def wizard_login(body: dict = Body(...)):
        return wizard.set_login(body.get("username", ""), body.get("password", ""))

    @app.post("/api/wizard/connect")
    def wizard_connect(body: dict = Body(...)):
        return wizard.connect(body.get("code", ""))

    @app.post("/api/wizard/child")
    def wizard_child(body: dict = Body(...)):
        return wizard.select_child(
            body.get("child_id", ""),
            body.get("name", ""),
            body.get("class_name", ""),
        )

    @app.post("/api/wizard/skip-child")
    def wizard_skip_child():
        return wizard.skip_child()

    @app.post("/api/wizard/back")
    def wizard_back():
        return wizard.back()

    @app.post("/api/wizard/reset")
    def wizard_reset(body: dict = Body(default=None)):
        return wizard.reset((body or {}).get("connection_id") or None)

    @app.post("/api/wizard/start")
    def wizard_start():
        return wizard.start_new()

    @app.post("/api/wizard/cancel")
    def wizard_cancel():
        return wizard.cancel()
