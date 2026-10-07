import json

import pytest

from regulus.config import AuthMode, ConfigError, load

SECRET = "s" * 40
ENVV = {"REGULUS_CSRF_SECRET": SECRET}


def fields(e: pytest.ExceptionInfo[ConfigError]) -> set[str]:
    return {f for f, _ in e.value.problems}


def test_defaults_are_safe():
    c = load(env=ENVV)
    assert c.host == "127.0.0.1" and c.port == 8765 and c.auth_mode is AuthMode.NONE
    assert c.claim_ttl_seconds == 900 and c.observation_buffer == 1000


def test_secret_required_and_long_enough():
    with pytest.raises(ConfigError) as e:
        load(env={})
    assert fields(e) == {"csrf_secret"}
    with pytest.raises(ConfigError) as e:
        load(env={"REGULUS_CSRF_SECRET": "short"})
    assert fields(e) == {"csrf_secret"}


@pytest.mark.parametrize(
    "var,val,field",
    [
        ("REGULUS_PORT", "0", "port"),
        ("REGULUS_PORT", "70000", "port"),
        ("REGULUS_PORT", "abc", "port"),
        ("REGULUS_CLAIM_TTL_SECONDS", "0", "claim_ttl_seconds"),
        ("REGULUS_OBSERVATION_BUFFER", "-1", "observation_buffer"),
        ("REGULUS_AUTH_MODE", "open", "auth_mode"),
        ("REGULUS_HOST", "0.0.0.0", "host"),
    ],
)
def test_invalid_values_rejected_by_field(var, val, field):
    with pytest.raises(ConfigError) as e:
        load(env={**ENVV, var: val})
    assert fields(e) == {field}


def test_non_loopback_needs_external_and_dev_header_never_does():
    assert load(env={**ENVV, "REGULUS_HOST": "0.0.0.0", "REGULUS_AUTH_MODE": "external"})
    with pytest.raises(ConfigError):
        load(env={**ENVV, "REGULUS_HOST": "0.0.0.0", "REGULUS_AUTH_MODE": "dev_header"})


def test_errors_never_carry_values():
    bad = "UNIQUE-BAD-VALUE-123"
    for env in (
        {**ENVV, "REGULUS_AUTH_MODE": bad},
        {**ENVV, "REGULUS_PORT": bad},
        {"REGULUS_CSRF_SECRET": bad},
        {**ENVV, "REGULUS_HOST": bad},
    ):
        with pytest.raises(ConfigError) as e:
            load(env=env)
        assert bad not in str(e.value) and bad not in repr(e.value.problems)


def test_env_overrides_file(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"port": 9000, "claim_ttl_seconds": 60}))
    c = load(f, {**ENVV, "REGULUS_PORT": "9100"})
    assert c.port == 9100 and c.claim_ttl_seconds == 60


@pytest.mark.parametrize("key", ["csrf_secret", "api_token", "db_password", "signing_key"])
def test_secret_looking_key_in_file_rejected(tmp_path, key):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({key: SECRET}))
    with pytest.raises(ConfigError) as e:
        load(f, ENVV)
    assert key in fields(e) and SECRET not in str(e.value)


def test_unknown_key_and_bad_file_rejected(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"surprise": 1}))
    with pytest.raises(ConfigError) as e:
        load(f, ENVV)
    assert fields(e) == {"surprise"}
    f.write_text("{not json")
    with pytest.raises(ConfigError) as e:
        load(f, ENVV)
    assert fields(e) == {"config_file"}
    with pytest.raises(ConfigError):
        load(tmp_path / "missing.json", ENVV)


def test_effective_masks_secret_and_never_repeats_it():
    c = load(env=ENVV)
    out = json.dumps(c.effective())
    assert SECRET not in out and SECRET not in repr(c) and SECRET not in c.model_dump_json()
    assert c.effective()["csrf_secret"] == "<set>"


def test_schedule_from_file(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"schedule": {"max_attempts": 2}}))
    assert load(f, ENVV).schedule.max_attempts == 2
    f.write_text(json.dumps({"schedule": {"nope": 2}}))
    with pytest.raises(ConfigError):
        load(f, ENVV)


@pytest.mark.parametrize(
    "doc",
    [
        {"port": "8000"},
        {"port": True},
        {"claim_ttl_seconds": 1.5},
        {"host": 5},
        {"auth_mode": "NONE"},
        {"state_dir": 5},
        {"retention_policy": 7},
    ],
)
def test_wrong_types_in_the_file_are_rejected_not_coerced(tmp_path, doc):
    f = tmp_path / "c.json"
    f.write_text(json.dumps(doc))
    with pytest.raises(ConfigError) as e:
        load(f, ENVV)
    assert fields(e) == set(doc)


@pytest.mark.parametrize("val", [" 80 ", "8e3", "+80", "0x50", "1_000"])
def test_environment_integers_are_parsed_strictly(val):
    with pytest.raises(ConfigError) as e:
        load(env={**ENVV, "REGULUS_PORT": val})
    assert fields(e) == {"port"}
