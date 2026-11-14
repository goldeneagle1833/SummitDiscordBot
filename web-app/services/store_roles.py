"""Discord roles sold in the Summit Store (e.g. a season ticket).

When an order with a Discord role product is paid, a discord_role_add row
goes into the notifications outbox; the bot's StoreNotificationsCog picks it
up and gives the buyer that role in the Summit server. Marking the order
refunded queues a discord_role_remove row that takes the role back.

A listing set to "current season ticket" gives whichever season ticket role
is on sale when the order is paid (services/ticket_roles.py). The role
actually given is saved on the order item, so a refund takes back that one.

Row shape: recipient = buyer's Discord user id, body = role id,
subject = what it's for (shown in the admin alert if the bot can't do it).
"""

import logging

from repositories.store import CURRENT_SEASON_TICKET, StoreRepository
from services.ticket_roles import selling_ticket_role

logger = logging.getLogger(__name__)

ROLE_ADD = "discord_role_add"
ROLE_REMOVE = "discord_role_remove"


def resolve_role_id(role_id: str | None) -> str | None:
    """A product's role ID, with "current season ticket" looked up."""
    if role_id == CURRENT_SEASON_TICKET:
        role = selling_ticket_role()
        return str(role["role_id"]) if role else None
    return role_id or None


def _role_items(order: dict) -> list[dict]:
    return [
        i for i in order.get("items") or []
        if StoreRepository.is_role_product(i) and i.get("discord_role_id")
    ]


def _enabled(order: dict) -> bool:
    return not str(order["user_id"]).startswith("google_")


def queue_role_grants(repo: StoreRepository, order: dict) -> int:
    """Queue the bot to give the buyer every role in a paid order."""
    if not _enabled(order):
        return 0
    queued = 0
    for item in _role_items(order):
        role_id = resolve_role_id(item["discord_role_id"])
        if role_id is None:
            # Nothing on sale: a person has to pick the role by hand
            repo.enqueue_notification(
                order["id"], "discord_admin", "store-admins",
                f"No season ticket role for order {order['order_number']}",
                f"**{order['username']}** (<@{order['user_id']}>) bought "
                f"{item['product_name']}, but no season ticket role is set up. "
                f"Run `!ticket_role Season N Ticket`, then give them the role by hand.",
            )
            continue
        if item.get("id"):
            repo.set_granted_role(item["id"], role_id)
        repo.enqueue_notification(
            order["id"], ROLE_ADD, str(order["user_id"]),
            f"Give {item['product_name']} role for order {order['order_number']}",
            role_id,
        )
        queued += 1
    if queued:
        repo.log_action("store-roles", "system", "queue_role_grant",
                        f"order={order['order_number']} roles={queued}")
    return queued


def queue_role_removals(repo: StoreRepository, order: dict) -> int:
    """Queue the bot to take back the roles of a refunded order."""
    if not _enabled(order):
        return 0
    queued = 0
    for item in _role_items(order):
        role_id = item.get("granted_role_id")
        if not role_id and item["discord_role_id"] != CURRENT_SEASON_TICKET:
            role_id = item["discord_role_id"]
        if not role_id:
            continue  # never given
        repo.enqueue_notification(
            order["id"], ROLE_REMOVE, str(order["user_id"]),
            f"Remove {item['product_name']} role for order {order['order_number']}",
            str(role_id),
        )
        queued += 1
    if queued:
        repo.log_action("store-roles", "system", "queue_role_removal",
                        f"order={order['order_number']} roles={queued}")
    return queued
