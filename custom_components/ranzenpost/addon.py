from __future__ import annotations

from aiohasupervisor.models import AddonsOptions

from .const import ADDON_SLUG


def is_ranzenpost_addon(slug: str) -> bool:
    return slug == ADDON_SLUG or slug.endswith(f"_{ADDON_SLUG}")


def addon_hostname(slug: str) -> str:
    return slug.replace("_", "-")


async def entry_addon(client, host: str):
    ours = [addon for addon in await client.addons.list() if is_ranzenpost_addon(addon.slug)]
    wanted = str(host or "").lower()
    matching = [addon for addon in ours if addon_hostname(addon.slug) == wanted]
    if len(matching) == 1:
        return matching[0]
    return ours[0] if len(ours) == 1 else None


async def set_auto_update(client, slug: str, enabled: bool) -> None:
    await client.addons.set_addon_options(slug, AddonsOptions(auto_update=enabled))
