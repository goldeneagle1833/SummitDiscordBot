"""Test that all API endpoints have explicit auth decisions.

When adding a new endpoint, you must either:
1. Add an auth decorator (@require_auth, @require_api_key, @require_admin)
2. Add the endpoint to KNOWN_PUBLIC_ENDPOINTS below (conscious opt-in to public)

This prevents accidentally exposing endpoints without authentication.
"""

import pytest

# Endpoints intentionally public (read-only data, auth flows, status, etc.)
# To make a new endpoint public, add it here with a comment explaining why.
KNOWN_PUBLIC_ENDPOINTS = {
    # -- Status / health --
    "api.misc.status",
    "api.misc.recent_event",
    "api.misc.database_status",

    # -- Auth flows (must be public) --
    "api.misc.me",
    "api.misc.logout",
    "auth.login",
    "auth.discord_login",
    "auth.discord_callback",
    "auth.logout",
    "auth.google_login",
    "auth.google_callback",

    # -- Leaderboards (public read-only) --
    "api.leaderboard.get_leaderboard",
    "api.leaderboard.get_event_leaderboard",
    "api.leaderboard.get_combined_leaderboard",
    "api.leaderboard.get_paper_leaderboard",
    "api.leaderboard.get_paper_event_leaderboard",
    "api.leaderboard.get_elo_distribution",
    "api.leaderboard.get_leaderboard_sources",
    "api.leaderboard.get_source_leaderboard",
    "api.leaderboard.get_events",
    "api.leaderboard.get_player_event_stats",
    "api.leaderboard.get_archived_event_leaderboard",
    "api.leaderboard.get_season_leaderboard",
    "api.leaderboard.get_limited_leaderboard",
    "api.leaderboard.get_archived_limited_events",
    "api.leaderboard.get_archived_limited_leaderboard",

    # -- Card points (public, pilot-gated) --
    "api.card_points.get_card_points_public",
    "api.card_points.get_card_points_history",
    "api.card_points.check_deck",

    # -- Match history (public read-only) --
    "api.matches.available_dates",
    "api.matches.match_history",

    # -- Player profiles (public read-only) --
    "api.players.player_api",
    "api.players.search_players",
    "api.players.deck_snapshot",
    "api.players.get_deck_stats",
    "api.players.set_display_name",
    "api.players.get_profile_visibility",
    "api.players.set_profile_visibility",
    "api.players.reset_own_profile",
    "api.players.undo_profile_reset",
    "api.players.delete_own_account",
    "api.players.get_nav_prefs",
    "api.players.set_nav_prefs",
    "api.players.player_avatar_stats",
    "api.players.get_blocked_users",
    "api.players.block_user",
    "api.players.unblock_user",

    # -- Card / avatar stats (public read-only) --
    "api.cards.get_cards",
    "api.cards.get_live_popular_cards",
    "api.cards.get_element_filters",
    "api.cards.get_elements",
    "api.cards.get_card_stats",
    "api.cards.get_card_popularity",
    "api.cards.get_all_cards_popularity",
    "api.cards.get_deck_composition",
    "api.cards.get_played_winrate_filters",
    "api.cards.get_played_winrate_season_stats",
    "api.cards.get_played_winrates",
    "api.avatars.get_avatar_image_files",
    "api.avatars.get_avatar_filters",
    "api.avatars.get_all_avatars",
    "api.avatars.get_avatar_top_players",
    "api.avatars.get_avatar",
    "api.avatars.get_avatar_popularity",
    "api.avatars.get_all_avatars_popularity",
    "api.avatars.get_avatar_deck_composition",
    "api.avatars.get_avatar_elo_matrix",
    "api.avatars.get_avatars_elo_breakdown",
    "api.avatars.get_elo_breakdown_matches",
    "api.avatars.get_play_draw_stats",
    "api.avatars.get_season_stats",
    "api.avatars.get_avatar_matchups",
    "api.avatars.list_all_avatars",
    "api.avatars.get_elo_bracket_matrix",

    # -- Events / tournaments (public read-only) --
    "api.events.list_top8_events",
    "api.events.get_event_detail",

    # -- Curios (auth checked internally per-method) --
    "api.curios.list_entries",
    "api.curios.list_sets",
    "api.curios.create_entry",
    "api.curios.update_entry",
    "api.curios.delete_entry",
    "api.curios.create_set",

    # -- Deck recommendations (public read-only) --
    "api.deck_rec.get_decks",
    "api.deck_rec.get_deck_info",
    "api.deck_rec.get_recommendations",
    "api.deck_rec.staff_pick",

    # -- Fun stats (public read-only) --
    "api.fun_stats.get_fun_stats_filters",
    "api.fun_stats.get_fun_stats",

    # -- Community / misc (public read-only) --
    "api.misc.community",
    "api.misc.youtube_videos",
    "api.misc.spotlight",
    "api.misc.event_spotlight",

    # -- Streamers (public read-only) --
    "api.streamers.list_streamers",
    "api.streamers.streamer_banner",

    # -- Analytics (public tracking endpoints) --
    "api.analytics.page_view",
    "api.analytics.banner_click",
    "api.analytics.heartbeat",
    "api.analytics.active_banners",

    # -- Seasons (public browse) --
    "api.seasons.browse_seasons",
    "api.seasons.get_player_seasons",
    "api.seasons.get_season",
    "api.seasons.get_season_members",

    # -- Match reporting (auth checked internally) --
    "api.match_reporting.submit_match_report",
    "api.match_reporting.confirm_match_report",
    "api.match_reporting.deny_match_report",
    "api.match_reporting.get_pending_confirmations",
    "api.match_reporting.search_opponents",
    "api.match_reporting.edit_match_comment",

    # -- Limited (API key checked internally / public read-only) --
    "api.limited.post_report_match",
    "api.limited.post_user_run",
    "api.limited.post_end_run",
    "api.limited.get_user_status",
    "api.limited.get_run_matchups_endpoint",
    "api.limited.get_match_history",

    # -- Static file serving --
    "static",
    "avatar_images",
    "card_images",

    # -- Explorer Standings (public read-only) --
    "api.explorer.get_seasons",
    "api.explorer.get_season_events",
    "api.explorer.get_leaderboard",

    # -- Rumble (public read-only) --
    "api.rumble.get_rumble",

    # -- Deck Builder (public tool) --
    "api.deck_builder.all_cards",
    "api.deck_builder.fetch_deck",

    # -- Store (public catalog + Stripe webhook verified by signature) --
    "api.store.list_products",
    "api.store.stripe_webhook",

    # -- OG previews (bot crawlers only, public read-only) --
    "og_preview.og_events_list",
    "og_preview.og_event_detail",
    "og_preview.og_deck_rec_list",
    "og_preview.og_deck_detail",
}


def _has_auth_marker(view_func):
    """Check if a view function was decorated with an auth decorator."""
    return getattr(view_func, "_auth_required", False)


class TestEndpointAuthCoverage:
    def test_all_endpoints_have_auth_or_are_allowlisted(self, app):
        """Every endpoint must have an auth decorator or be in KNOWN_PUBLIC_ENDPOINTS."""
        unprotected = []

        for rule in app.url_map.iter_rules():
            endpoint = rule.endpoint
            view_func = app.view_functions.get(endpoint)
            if view_func is None:
                continue

            if _has_auth_marker(view_func):
                continue

            if endpoint in KNOWN_PUBLIC_ENDPOINTS:
                continue

            unprotected.append(f"{endpoint} ({rule.rule})")

        assert unprotected == [], (
            "Found endpoints without auth decorators that are NOT in "
            "KNOWN_PUBLIC_ENDPOINTS.\n"
            "Either add an auth decorator (@require_auth, @require_api_key, "
            "@require_admin) or explicitly add the endpoint to "
            "KNOWN_PUBLIC_ENDPOINTS in test_endpoint_auth.py:\n"
            + "\n".join(f"  - {ep}" for ep in sorted(unprotected))
        )

    def test_allowlist_has_no_stale_entries(self, app):
        """KNOWN_PUBLIC_ENDPOINTS should not contain endpoints that no longer exist."""
        registered = {rule.endpoint for rule in app.url_map.iter_rules()}
        stale = KNOWN_PUBLIC_ENDPOINTS - registered

        assert stale == set(), (
            "KNOWN_PUBLIC_ENDPOINTS contains endpoints that no longer exist "
            "in the app. Remove them:\n"
            + "\n".join(f"  - {ep}" for ep in sorted(stale))
        )

    def test_allowlist_has_no_protected_entries(self, app):
        """Endpoints with auth decorators should not be in the allowlist."""
        redundant = []
        for endpoint in sorted(KNOWN_PUBLIC_ENDPOINTS):
            view_func = app.view_functions.get(endpoint)
            if view_func and _has_auth_marker(view_func):
                redundant.append(endpoint)

        assert redundant == [], (
            "These endpoints have auth decorators but are also in "
            "KNOWN_PUBLIC_ENDPOINTS. Remove them from the allowlist:\n"
            + "\n".join(f"  - {ep}" for ep in redundant)
        )
