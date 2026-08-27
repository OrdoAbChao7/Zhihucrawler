from zhihu_app.gui.app import run_login_in_background


def test_login_failure_is_forwarded_to_error_callback():
    errors = []

    class BrokenSession:
        async def login(self):
            raise RuntimeError("browser unavailable")

    run_login_in_background(lambda: BrokenSession(), errors.append)
    assert str(errors[0]) == "browser unavailable"


def test_login_is_verified_before_success_callback():
    events = []

    class Session:
        async def login(self):
            events.append("login")

    class Verifier:
        def verify_login(self):
            events.append("verify")

    run_login_in_background(
        lambda: Session(),
        lambda error: events.append(f"error:{error}"),
        lambda session: events.append("success"),
        verifier_factory=lambda: Verifier(),
    )
    assert events == ["login", "verify", "success"]
