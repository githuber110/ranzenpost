from custom_components.ranzenpost.panels import app_panel_path


def test_the_app_panel_replaces_the_add_on_panel_path():
    assert app_panel_path({"app": object()}, "/hassio/ingress/local_ranzenpost") == "/app/local_ranzenpost"


def test_older_home_assistant_keeps_the_add_on_panel_path():
    assert app_panel_path({"hassio": object()}, "/hassio/ingress/local_ranzenpost") == "/hassio/ingress/local_ranzenpost"
    assert app_panel_path({"hassio": object(), "app": object()}, "/hassio/ingress/x") == "/hassio/ingress/x"
    assert app_panel_path(None, "/hassio/ingress/x") == "/hassio/ingress/x"


def test_other_paths_stay_as_they_are():
    assert app_panel_path({"app": object()}, "") == ""
    assert app_panel_path({"app": object()}, "/local_ranzenpost") == "/local_ranzenpost"
