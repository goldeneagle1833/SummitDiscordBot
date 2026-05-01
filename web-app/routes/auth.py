"""OAuth authentication routes for Discord and Google."""

import json
import logging
from urllib.parse import urlencode

import requests
from flask import Blueprint, redirect, url_for, session, request, render_template, jsonify

import webapp_config
from webapp_config import (
    DISCORD_CLIENT_ID,
    DISCORD_CLIENT_SECRET,
    DISCORD_REDIRECT_URI,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
)
from repositories.user_profiles import UserProfileRepository
from utils.auth import is_admin

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)



@auth_bp.route("/login")
def login():
    """Display login selection page."""
    return render_template("pages/login.html")


@auth_bp.route("/discord")
def discord_login():
    """Redirect user to Discord OAuth authorization."""
    if not DISCORD_CLIENT_ID:
        logger.error("DISCORD_CLIENT_ID not configured")
        return "OAuth not configured", 500

    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify email",  # Request email scope to get user's email
    }
    auth_url = f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"
    return redirect(auth_url)


@auth_bp.route("/discord/callback")
def discord_callback():
    """Handle Discord OAuth callback."""
    error = request.args.get("error")
    if error:
        logger.error(f"Discord OAuth error: {error}")
        return redirect(webapp_config.FRONTEND_URL)

    code = request.args.get("code")
    if not code:
        logger.error("No code received from Discord")
        return redirect(webapp_config.FRONTEND_URL)

    # Exchange code for access token
    token_url = "https://discord.com/api/oauth2/token"
    token_data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI,
    }

    try:
        token_response = requests.post(token_url, data=token_data)
        token_response.raise_for_status()
        tokens = token_response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to get Discord token: {e}")
        return redirect(webapp_config.FRONTEND_URL)

    access_token = tokens.get("access_token")
    if not access_token:
        logger.error("No access token in Discord response")
        return redirect(webapp_config.FRONTEND_URL)

    # Get user info from Discord
    user_url = "https://discord.com/api/users/@me"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        user_response = requests.get(user_url, headers=headers)
        user_response.raise_for_status()
        user_data = user_response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to get Discord user info: {e}")
        return redirect(webapp_config.FRONTEND_URL)

    # Store user info in session (permanent = survives browser close)
    session.permanent = True
    session["user_id"] = int(user_data["id"])
    session["username"] = user_data["username"]
    session["avatar"] = user_data.get("avatar")
    session["auth_provider"] = "discord"

    # Save comprehensive user profile to database (non-blocking)
    try:
        profile_repo = UserProfileRepository()
        profile_repo.upsert_profile(
            user_id=str(session["user_id"]),
            display_name=session["username"],
            avatar=session["avatar"],
            provider="discord",
            email=user_data.get("email"),
            email_verified=user_data.get("verified"),
            discriminator=user_data.get("discriminator"),
            flags=user_data.get("flags"),
            public_flags=user_data.get("public_flags"),
            raw_oauth_data=json.dumps(user_data),
        )
    except Exception as e:
        logger.error(f"Failed to save user profile: {e}")

    logger.info(f"User {user_data['username']} (ID: {user_data['id']}) logged in")

    return redirect(webapp_config.FRONTEND_URL)


@auth_bp.route("/logout")
def logout():
    """Clear session and log out user."""
    username = session.get("username", "Unknown")
    session.clear()
    logger.info(f"User {username} logged out")
    return redirect(url_for("pages.home"))


@auth_bp.route("/google")
def google_login():
    """Redirect user to Google OAuth authorization."""
    if not GOOGLE_CLIENT_ID:
        logger.error("GOOGLE_CLIENT_ID not configured")
        return "Google OAuth not configured", 500

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return redirect(auth_url)


@auth_bp.route("/google/callback")
def google_callback():
    """Handle Google OAuth callback."""
    error = request.args.get("error")
    if error:
        logger.error(f"Google OAuth error: {error}")
        return redirect(webapp_config.FRONTEND_URL)

    code = request.args.get("code")
    if not code:
        logger.error("No code received from Google")
        return redirect(webapp_config.FRONTEND_URL)

    # Exchange code for access token
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": GOOGLE_REDIRECT_URI,
    }

    try:
        token_response = requests.post(token_url, data=token_data)
        token_response.raise_for_status()
        tokens = token_response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to get Google token: {e}")
        return redirect(webapp_config.FRONTEND_URL)

    access_token = tokens.get("access_token")
    if not access_token:
        logger.error("No access token in Google response")
        return redirect(webapp_config.FRONTEND_URL)

    # Get user info from Google
    user_url = "https://www.googleapis.com/oauth2/v2/userinfo"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        user_response = requests.get(user_url, headers=headers)
        user_response.raise_for_status()
        user_data = user_response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to get Google user info: {e}")
        return redirect(webapp_config.FRONTEND_URL)

    # Store user info in session (permanent = survives browser close)
    session.permanent = True
    # Use Google ID prefixed with 'google_' to distinguish from Discord IDs
    google_user_id = f"google_{user_data['id']}"
    session["user_id"] = google_user_id
    session["username"] = user_data.get("name", user_data.get("email", "Unknown"))
    session["avatar"] = user_data.get("picture")
    session["auth_provider"] = "google"

    # Save comprehensive user profile to database (non-blocking)
    try:
        profile_repo = UserProfileRepository()
        profile_repo.upsert_profile(
            user_id=google_user_id,
            display_name=session["username"],
            avatar=session["avatar"],
            provider="google",
            email=user_data.get("email"),
            email_verified=user_data.get("verified_email"),
            given_name=user_data.get("given_name"),
            family_name=user_data.get("family_name"),
            locale=user_data.get("locale"),
            raw_oauth_data=json.dumps(user_data),
        )
    except Exception as e:
        logger.error(f"Failed to save user profile: {e}")

    logger.info(
        f"User {session['username']} (Google ID: {user_data['id']}) logged in via Google"
    )

    return redirect(webapp_config.FRONTEND_URL)
