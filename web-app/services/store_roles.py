"""Discord roles sold in the Summit Store (e.g. a season ticket).

When an order with a Discord role product is paid, a discord_role_add row
goes into the notifications outbox; the bot's StoreNotificationsCog picks it
up and gives the buyer that role in the Summit server. Marking the order
refunded queues a discord_role_remove row that takes the role back.

Row shape: recipient = buyer's Discord user id, body = role id,
subject = what it's for (shown in the admin alert if the bot can't do it).
"""

import logging

from repositories.store import StoreRepository

logger = logging.getLogger(__name__)

ROLE_ADD = "discord_role_add"
ROLE_REMOVE = "discord_role_remove"


def _role_items(order: dict) -> list[dict]:
    return [
        i for i in order.get("items") or []
        if StoreRepository.is_role_product(i) and i.get("discord_role_id")
    ]


def _queue(repo: StoreRepository, order: dict, channel: str, verb: str) -> int:
    if str(order["user_id"]).startswith("google_"):
        return 0
    queued = 0
    for item in _role_items(order):
        repo.enqueue_notification(
            order["id"], channel, str(order["user_id"]),
            f"{verb} {item['product_name']} role for order {order['order_number']}",
            str(item["discord_role_id"]),
        )
        queued += 1
    return queued


def queue_role_grants(repo: StoreRepository, order: dict) -> int:
    """Queue the bot to give the buyer every role in a paid order."""
    count = _queue(repo, order, ROLE_ADD, "Give")
    if count:
        repo.log_action("store-roles", "system", "queue_role_grant",
                        f"order={order['order_number']} roles={count}")
    return count


def queue_role_removals(repo: StoreRepository, order: dict) -> int:
    """Queue the bot to take back the roles of a refunded order."""
    count = _queue(repo, order, ROLE_REMOVE, "Remove")
    if count:
        repo.log_action("store-roles", "system", "queue_role_removal",
                        f"order={order['order_number']} roles={count}")
    return count
