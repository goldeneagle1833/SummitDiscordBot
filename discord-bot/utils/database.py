"""
Database facade module.

Re-exports all functions from repositories and services layers
for backward compatibility. All existing imports like:

    from utils.database import winner_report, get_user_elo

continue to work unchanged.
"""

# Data access functions
from repositories.elo_repo import (  # noqa: F401
    get_db_connection,
    create_db,
    create_events_table,
    create_match_records_archive,
    create_ladder_challenge_table,
    create_active_pairings_table,
    migrate_to_dual_elo_system,
    get_active_event,
    get_user_elo,
    get_user_event_elo,
    get_user_paper_elo,
    get_user_paper_event_elo,
    get_past_events,
    get_event_archive_standings,
    get_top_16_user_ids,
    get_top_8_user_ids,
    get_total_match_count,
    get_event_match_count,
    get_player_event_match_count,
    get_event_participant_ids,
    has_player_played_event,
    get_ladder_challenge_today,
    save_ladder_challenge,
    complete_ladder_challenge,
    delete_ladder_challenge,
    reset_ladder_challenge_today,
    # Pairing functions
    save_pairing,
    get_active_pairing_for_user,
    get_opponent_from_pairing,
    get_pairing_between_players,
    validate_pairing,
    mark_pairing_reported,
    cancel_pairing,
    cleanup_old_pairings,
)

# Business logic functions
from services.elo_service import (  # noqa: F401
    update_elo,
    calculate_event_k_value,
    update_elo_db,
    update_elo_db_lifetime_only,
    update_elo_db_ladder,
    get_current_event_match_elo_snapshot,
    record_match,
    start_new_event,
    end_current_event,
    check_milestone,
    solo_match_report,
    recalculate_event_elo,
    get_match_players,
    correct_match_record,
    correct_limited_match_record,
    remove_match_record,
    remove_player as remove_player_service,
)

# Admin repo functions
from repositories.elo_repo import (  # noqa: F401
    set_player_event_elo,
    set_player_avatar_event_elo,
)

# Limited queue (arena draft mode) data access
from repositories.limited_repo import (  # noqa: F401
    create_limited_tables,
)

# Pilots (feature flags)
from services.pilots_service import is_pilot_active  # noqa: F401

# Audit logging
from repositories.audit_repo import log_admin_action  # noqa: F401

# Dust code system
from repositories.dust_repo import (  # noqa: F401
    create_dust_tables,
)

# Blocked users
from repositories.blocked_users_repo import (  # noqa: F401
    create_blocked_users_table,
    get_blocked_user_ids,
    is_blocked_pair,
)

# Community data access functions
from repositories.community_repo import (  # noqa: F401
    create_community_tables,
    add_discord_server,
    add_youtube_channel,
    add_website,
    remove_entry,
    get_all_discord_servers,
    get_all_youtube_channels,
    get_all_websites,
)
