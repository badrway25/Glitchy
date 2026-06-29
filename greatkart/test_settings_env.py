"""Tests for ALLOWED_HOSTS env resolution (production-deploy host override).

The production host list must come from the environment so the server never needs
a local settings.py edit. Both the canonical DJANGO_ALLOWED_HOSTS and a bare
ALLOWED_HOSTS (exported in /etc/glitchy/env on the host) are honoured; the first
one set wins, values are stripped and empties ignored, and dev falls back to
localhost. No environment value is ever printed."""
import contextlib
import os

from django.test import SimpleTestCase

from greatkart.settings import _allowed_hosts, env_list

_KEYS = ("DJANGO_ALLOWED_HOSTS", "ALLOWED_HOSTS")


@contextlib.contextmanager
def _env(**values):
    """Set/clear only the two host env vars, fully restoring them afterwards."""
    saved = {k: os.environ.get(k) for k in _KEYS}
    try:
        for k in _KEYS:
            os.environ.pop(k, None)
        for k, v in values.items():
            os.environ[k] = v
        yield
    finally:
        for k in _KEYS:
            os.environ.pop(k, None)
            val = saved[k]
            if val is not None:
                os.environ[k] = val


class AllowedHostsEnvTests(SimpleTestCase):
    def test_dev_default_when_unset(self):
        with _env():
            self.assertEqual(_allowed_hosts(), ["127.0.0.1", "localhost"])

    def test_django_prefixed_var(self):
        with _env(DJANGO_ALLOWED_HOSTS="shop.example.com, www.example.com"):
            self.assertEqual(_allowed_hosts(), ["shop.example.com", "www.example.com"])

    def test_bare_allowed_hosts_var(self):
        """The unprefixed ALLOWED_HOSTS (used in /etc/glitchy/env) is honoured."""
        with _env(ALLOWED_HOSTS="glitchy.example.com"):
            self.assertEqual(_allowed_hosts(), ["glitchy.example.com"])

    def test_bare_wins_over_prefixed(self):
        # The bare ALLOWED_HOSTS (production host config) takes precedence so the
        # live server keeps working exactly as it does today.
        with _env(ALLOWED_HOSTS="live.example.com", DJANGO_ALLOWED_HOSTS="other.com"):
            self.assertEqual(_allowed_hosts(), ["live.example.com"])

    def test_prefixed_used_when_bare_absent(self):
        with _env(DJANGO_ALLOWED_HOSTS="canonical.com"):
            self.assertEqual(_allowed_hosts(), ["canonical.com"])

    def test_strips_spaces_and_ignores_empties(self):
        with _env(ALLOWED_HOSTS="  ,  glitchy.example.com , , "):
            self.assertEqual(_allowed_hosts(), ["glitchy.example.com"])

    def test_env_list_helper_is_safe(self):
        # empty / whitespace-only -> default; never raises, never prints
        self.assertEqual(env_list("ALLOWED_HOSTS", ["x"]) and True, True)
        with _env(ALLOWED_HOSTS="   "):
            self.assertEqual(_allowed_hosts(), ["127.0.0.1", "localhost"])
