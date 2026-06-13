"""Per-user settings isolation at the service layer."""
from app import models
from app.security import hash_password
from app.services.settings_service import get_settings, update_settings


def _user(session, email):
    u = models.User(email=email, password_hash=hash_password("password123"))
    session.add(u)
    session.commit()
    return u.id


def test_settings_are_per_user(session):
    a = _user(session, "a@x.com")
    b = _user(session, "b@x.com")
    update_settings(session, a, {"fire_radius_miles": 99})
    assert get_settings(session, a)["fire_radius_miles"] == 99
    assert get_settings(session, b)["fire_radius_miles"] == 30.0  # default, unaffected


def test_unparseable_value_keeps_default(session):
    a = _user(session, "c@x.com")
    session.add(models.AppSetting(user_id=a, key="connectors_enabled", value="not-json{"))
    session.commit()
    assert isinstance(get_settings(session, a)["connectors_enabled"], dict)
