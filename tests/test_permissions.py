from types import SimpleNamespace
from bot.utils.permissions import is_guild_admin


def test_administrator_permission_gate():
    assert is_guild_admin(SimpleNamespace(guild=object(), user=SimpleNamespace(guild_permissions=SimpleNamespace(manage_guild=True))))
    assert not is_guild_admin(SimpleNamespace(guild=object(), user=SimpleNamespace(guild_permissions=SimpleNamespace(manage_guild=False))))
    assert not is_guild_admin(SimpleNamespace(guild=None, user=None))
