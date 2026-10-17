"""Baseline data (Section 5.5). Sports use the SAME schema as POST /audit/v1/sports."""
from app.config import DEFAULT_TIE_BREAK

SEED_SPORTS = {
    "football": {
        "sport_id": "football", "name": "Football", "scoring_model": "event",
        "periods": {"count": 2, "duration_minutes": 45},
        "scoring_events": {"goal": {"points": 1}},
        "draw_allowed": True, "overtime": {"policy": "none"},
        "tie_break_order": list(DEFAULT_TIE_BREAK),
        "roster": {"min_squad_size": 11, "max_squad_size": 25, "required_positions": {"gk": 1}},
    },
    "basketball": {
        "sport_id": "basketball", "name": "Basketball", "scoring_model": "event",
        "periods": {"count": 4, "duration_minutes": 12},
        "scoring_events": {"free_throw": {"points": 1}, "two_pointer": {"points": 2},
                           "three_pointer": {"points": 3}},
        "draw_allowed": False, "overtime": {"policy": "extra_time", "duration_minutes": 5},
        "tie_break_order": list(DEFAULT_TIE_BREAK),
        "roster": {"min_squad_size": 5, "max_squad_size": 15, "required_positions": {}},
    },
    "cricket": {
        "sport_id": "cricket", "name": "Cricket", "scoring_model": "innings",
        "periods": {"innings_per_team": 1, "overs_per_innings": 20,
                    "balls_per_over": 6, "wickets_per_innings": 10},
        "scoring_events": {
            "dot_ball": {"runs": 0, "legal_ball": True, "wicket": False},
            "single": {"runs": 1, "legal_ball": True, "wicket": False},
            "two": {"runs": 2, "legal_ball": True, "wicket": False},
            "four": {"runs": 4, "legal_ball": True, "wicket": False},
            "six": {"runs": 6, "legal_ball": True, "wicket": False},
            "wide": {"runs": 1, "legal_ball": False, "wicket": False},
            "no_ball": {"runs": 1, "legal_ball": False, "wicket": False},
            "wicket": {"runs": 0, "legal_ball": True, "wicket": True},
        },
        "draw_allowed": True, "overtime": {"policy": "super_over"},
        "tie_break_order": list(DEFAULT_TIE_BREAK),
        "roster": {"min_squad_size": 11, "max_squad_size": 18,
                   "required_positions": {"wicketkeeper": 1}},
    },
    "esports": {
        "sport_id": "esports", "name": "Esports", "scoring_model": "round",
        "periods": {"best_of": 3},
        "scoring_events": {"round_win": {"rounds": 1}},
        "draw_allowed": False, "overtime": {"policy": "none"},
        "tie_break_order": list(DEFAULT_TIE_BREAK),
        "roster": {"min_squad_size": 5, "max_squad_size": 8, "required_positions": {}},
    },
}

TENANTS = [
    {"id": "tenant-alpha", "name": "Alpha Sports", "logo_url": "https://example.invalid/alpha.png",
     "primary_color": "#0B5FFF", "secondary_color": "#FFB703"},
    {"id": "tenant-beta", "name": "Beta Athletics", "logo_url": "https://example.invalid/beta.png",
     "primary_color": "#C1121F", "secondary_color": "#F1FAEE"},
]

LEAGUES = [
    ("league-alpha-1", "tenant-alpha", "Alpha League One"),
    ("league-alpha-2", "tenant-alpha", "Alpha League Two"),
    ("league-beta-1", "tenant-beta", "Beta League One"),
]

CLUBS = [
    ("club-alpha-1", "tenant-alpha", "Alpha FC One", 31.5204, 74.3587),
    ("club-alpha-2", "tenant-alpha", "Alpha FC Two", 33.6844, 73.0479),
    ("club-beta-1", "tenant-beta", "Beta United", 24.8607, 67.0011),
]

PLAYERS = [
    ("player-alpha-1", "club-alpha-1", "tenant-alpha", "Ali Raza", "gk"),
    ("player-alpha-2", "club-alpha-2", "tenant-alpha", "Bilal Khan", "df"),
    ("player-beta-1", "club-beta-1", "tenant-beta", "Hamza Ahmed", "fw"),
]

DEMO_PASSWORD = "Nascon@26"
DEMO_USERS = [
    dict(email="admin@nascon.test", role="super_admin", display_name="Platform Admin",
         tenant_id=None, league_ids=[], club_id=None, player_id=None),
    dict(email="organizer@nascon.test", role="league_organizer", display_name="League Organizer",
         tenant_id="tenant-alpha", league_ids=["league-alpha-1"], club_id=None, player_id=None),
    dict(email="manager@nascon.test", role="club_manager", display_name="Club Manager",
         tenant_id="tenant-alpha", league_ids=[], club_id="club-alpha-1", player_id=None),
    dict(email="player@nascon.test", role="player", display_name="Player One",
         tenant_id="tenant-alpha", league_ids=[], club_id="club-alpha-1", player_id="player-alpha-1"),
    dict(email="viewer@nascon.test", role="viewer", display_name="Viewer",
         tenant_id="tenant-alpha", league_ids=[], club_id=None, player_id=None),
]

PRODUCT = {"product_id": "prod-jersey-001", "tenant_id": "tenant-alpha", "club_id": "club-alpha-1",
           "name": "Alpha FC Home Jersey", "category": "apparel"}
DEFAULT_STOCK = {"var-jersey-001-M": 1, "var-jersey-001-L": 5}
VARIANT_ATTRS = {"var-jersey-001-M": {"size": "M", "color": "blue"},
                 "var-jersey-001-L": {"size": "L", "color": "blue"}}
PRICE_MINOR = 450000
