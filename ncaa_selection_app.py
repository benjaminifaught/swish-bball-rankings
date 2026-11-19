"""SWISH: Schedule-Weighted Independent Selection & Seeding Hierarchy.

Requires Python 3.9 or newer.
"""

import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Optional
import numpy as np
import pandas as pd
import requests
from dash import Dash, ctx, dash_table, dcc, html, Input, Output, State

# ==========================================
# 1. POINT LEDGER & RULEBOOK CONSTANTS
# ==========================================
POINT_LEDGER = {
    1: {"W": {"H": 6.0, "N": 7.5, "A": 9.0}, "L": {"H": -1.0, "N": -0.5, "A": 0.0}},
    2: {"W": {"H": 4.0, "N": 5.0, "A": 6.5}, "L": {"H": -2.0, "N": -1.5, "A": -1.0}},
    3: {"W": {"H": 2.0, "N": 2.5, "A": 3.5}, "L": {"H": -3.5, "N": -2.5, "A": -2.0}},
    4: {"W": {"H": 0.5, "N": 1.0, "A": 1.5}, "L": {"H": -5.0, "N": -4.0, "A": -3.0}},
    5: {"W": {"H": 0.0, "N": 0.25, "A": 0.5}, "L": {"H": -8.0, "N": -6.5, "A": -5.0}},
}

def get_tier(colley_rank: int) -> int:
    if colley_rank <= 25:
        return 1
    elif colley_rank <= 60:
        return 2
    elif colley_rank <= 120:
        return 3
    elif colley_rank <= 200:
        return 4
    return 5

def get_dominance_bonus(reg_conf_losses: int) -> float:
    if reg_conf_losses <= 1:
        return 12.0
    elif reg_conf_losses == 2:
        return 8.0
    elif reg_conf_losses == 3:
        return 4.0
    return 0.0


def is_enabled(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


# ==========================================
# 2. LIVE ESPN SCOREBOARD FETCHER (D-I GAMES)
# ==========================================
ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/"
    "mens-college-basketball/scoreboard"
)

ESPN_CONFERENCE_NAMES = {
    "1": "America East Conference",
    "2": "Atlantic Coast Conference",
    "3": "Atlantic 10 Conference",
    "4": "Big East Conference",
    "5": "Big Sky Conference",
    "6": "Big South Conference",
    "7": "Big Ten Conference",
    "8": "Big 12 Conference",
    "9": "Big West Conference",
    "10": "Coastal Athletic Association",
    "11": "Conference USA",
    "12": "Ivy League",
    "13": "Metro Atlantic Athletic Conference",
    "14": "Mid-American Conference",
    "16": "Mid-Eastern Athletic Conference",
    "18": "Missouri Valley Conference",
    "19": "Northeast Conference",
    "20": "Ohio Valley Conference",
    "21": "Pac-12 Conference",
    "22": "Patriot League",
    "23": "Southeastern Conference",
    "24": "Southern Conference",
    "25": "Southland Conference",
    "26": "Southwestern Athletic Conference",
    "27": "Sun Belt Conference",
    "29": "West Coast Conference",
    "30": "United Athletic Conference",
    "44": "Mountain West Conference",
    "45": "Horizon League",
    "46": "Atlantic Sun Conference",
    "49": "Summit League",
    "62": "American Athletic Conference",
}
DIVISION_I_CONFERENCES = frozenset(ESPN_CONFERENCE_NAMES.values())
LEGACY_DATA_WARNING = False
CONFERENCE_ALIASES = {
    "A-10": "Atlantic 10 Conference",
    "ACC": "Atlantic Coast Conference",
    "Big 12": "Big 12 Conference",
    "Big East": "Big East Conference",
    "Big Ten": "Big Ten Conference",
    "CUSA": "Conference USA",
    "MAC": "Mid-American Conference",
    "MVC": "Missouri Valley Conference",
    "MWC": "Mountain West Conference",
    "SEC": "Southeastern Conference",
    "SWAC": "Southwestern Athletic Conference",
    "WCC": "West Coast Conference",
}


def get_conference_name(conference_id) -> str:
    conference_id = str(conference_id)
    return ESPN_CONFERENCE_NAMES.get(conference_id, CONFERENCE_ALIASES.get(conference_id, conference_id))


def basketball_season_year(date_value) -> int:
    date_text = str(date_value).strip()
    parsed_date = None
    for date_format in ("%Y%m%d", "%Y-%m-%d"):
        try:
            parsed_date = datetime.strptime(date_text[:10], date_format)
            break
        except ValueError:
            continue
    if parsed_date is None:
        try:
            parsed_date = datetime.fromisoformat(date_text.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError as exc:
            raise ValueError(f"Invalid game date: {date_value}") from exc
    return parsed_date.year if parsed_date.month >= 8 else parsed_date.year - 1


def latest_started_basketball_season_year(today: Optional[datetime] = None) -> int:
    today = today or datetime.now()
    return today.year if today.month >= 11 else today.year - 1


def basketball_season_date_bounds(
    season_start_year: int,
    today: Optional[datetime] = None,
):
    try:
        season_start_year = int(season_start_year)
    except (TypeError, ValueError) as exc:
        raise ValueError("Select a valid basketball season.") from exc

    today = today or datetime.now()
    latest_season_year = latest_started_basketball_season_year(today)
    if season_start_year < 2010 or season_start_year > latest_season_year:
        raise ValueError("Select a season from the available list.")

    start_date = datetime(season_start_year, 11, 1)
    end_date = min(datetime(season_start_year + 1, 4, 15), today)
    if start_date > today:
        raise ValueError("That basketball season has not started yet.")
    return start_date, end_date


def field_size_for_season(season_start_year: int) -> int:
    return 76 if int(season_start_year) >= 2026 else 68


def season_start_year_from_games(games_df: pd.DataFrame) -> int:
    if not games_df.empty:
        return int(games_df["date"].map(basketball_season_year).max())
    return latest_started_basketball_season_year()


def load_division_i_roster() -> pd.DataFrame:
    if not os.path.exists("teams.csv"):
        return pd.DataFrame(columns=["team", "conference", "is_auto_bid", "power_opponents_declined"])
    teams_df = pd.read_csv("teams.csv")
    teams_df["conference"] = teams_df["conference"].map(get_conference_name)
    teams_df = teams_df[teams_df["conference"].isin(DIVISION_I_CONFERENCES)].copy()
    teams_df["is_auto_bid"] = False
    if "power_opponents_declined" not in teams_df:
        teams_df["power_opponents_declined"] = False
    return teams_df[
        ["team", "conference", "is_auto_bid", "power_opponents_declined"]
    ].drop_duplicates("team", keep="last")


def fetch_espn_season_games(start_date: str = "20261102", end_date: Optional[str] = None):
    """
    Fetches completed NCAA Division I men's basketball games from ESPN's public
    scoreboard JSON endpoint between start_date and end_date. Accepts YYYYMMDD
    or YYYY-MM-DD dates and saves clean teams.csv and games.csv files locally.
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")

    def parse_date(date_value: str, label: str) -> datetime:
        normalized_value = date_value.strip()
        for date_format in ("%Y%m%d", "%Y-%m-%d"):
            try:
                return datetime.strptime(normalized_value, date_format)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(normalized_value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
        raise ValueError(f"{label} must use YYYY-MM-DD format.")

    dt_start = parse_date(start_date, "Start date")
    dt_end = parse_date(end_date, "End date")
    if dt_end < dt_start:
        raise ValueError("End date must be on or after the start date.")
    if basketball_season_year(dt_start) != basketball_season_year(dt_end):
        raise ValueError("Start and end dates must be within the same August-to-July basketball season.")
    if (dt_end - dt_start).days >= 366:
        raise ValueError("Choose a date range of 366 days or less for one season.")

    date_strings = [
        (dt_start + timedelta(days=offset)).strftime("%Y%m%d")
        for offset in range((dt_end - dt_start).days + 1)
    ]

    def fetch_scoreboard(date_str: str):
        params = {"dates": date_str, "groups": "50", "limit": "500"}
        try:
            resp = requests.get(ESPN_SCOREBOARD_URL, params=params, timeout=15)
            resp.raise_for_status()
            return date_str, resp.json()
        except requests.RequestException as exc:
            raise RuntimeError(f"ESPN request failed for {date_str}: {exc}") from exc

    with ThreadPoolExecutor(max_workers=min(6, len(date_strings))) as executor:
        scoreboards = executor.map(fetch_scoreboard, date_strings)

        teams_meta = {
            row["team"]: row
            for row in load_division_i_roster().to_dict("records")
        }
        game_rows = []
        for date_str, data in scoreboards:
            for event in data.get("events", []):
                comps = event.get("competitions", [])
                if not comps:
                    continue
                comp = comps[0]
                status_type = comp.get("status", {}).get("type", {})
                if not status_type.get("completed", False):
                    continue
                season_type = str(event.get("season", {}).get("type", ""))
                if season_type != "2":
                    continue

                competitors = comp.get("competitors", [])
                if len(competitors) != 2:
                    continue
                competitor_conference_ids = [
                    str(competitor.get("team", {}).get("conferenceId", ""))
                    for competitor in competitors
                ]
                if not all(conference_id in ESPN_CONFERENCE_NAMES for conference_id in competitor_conference_ids):
                    continue

                neutral_site = bool(comp.get("neutralSite", False))
                conf_comp = bool(comp.get("conferenceCompetition", False))
                note_headlines = [n.get("headline", "") for n in comp.get("notes", [])]
                notes = " ".join(note_headlines).lower()
                is_conf_tourney = conf_comp and any(
                    marker in notes for marker in ("championship", "tournament", "playoff")
                )
                is_conf_tourney_final = is_conf_tourney and any(
                    re.search(r"(?:^|\s)final\s*$", headline, re.IGNORECASE)
                    for headline in note_headlines
                )

                parsed = []
                for c in competitors:
                    t_info = c.get("team", {})
                    t_name = t_info.get("location") or t_info.get("displayName")
                    conference = get_conference_name(t_info.get("conferenceId", "Independent"))
                    home_away = c.get("homeAway", "home")
                    won = bool(c.get("winner", False))
                    parsed.append({
                        "team": t_name,
                        "conference": conference,
                        "home_away": home_away,
                        "won": won,
                    })
                    if t_name not in teams_meta:
                        teams_meta[t_name] = {
                            "team": t_name,
                            "conference": conference,
                            "is_auto_bid": False,
                            "power_opponents_declined": False,
                        }
                    else:
                        teams_meta[t_name]["conference"] = conference

                t_a, t_b = parsed[0], parsed[1]
                if is_conf_tourney_final:
                    final_winners = [team for team in parsed if team["won"]]
                    if len(final_winners) == 1:
                        teams_meta[final_winners[0]["team"]]["is_auto_bid"] = True

                loc_a = "N" if is_conf_tourney or neutral_site else ("H" if t_a["home_away"] == "home" else "A")
                loc_b = "N" if is_conf_tourney or neutral_site else ("H" if t_b["home_away"] == "home" else "A")

                game_rows.append({
                    "date": date_str,
                    "team": t_a["team"],
                    "opponent": t_b["team"],
                    "location": loc_a,
                    "won": t_a["won"],
                    "is_conf": conf_comp,
                    "is_conf_tourney": is_conf_tourney,
                    "is_conf_tourney_final": is_conf_tourney_final,
                    "season_type": 2,
                })
                game_rows.append({
                    "date": date_str,
                    "team": t_b["team"],
                    "opponent": t_a["team"],
                    "location": loc_b,
                    "won": t_b["won"],
                    "is_conf": conf_comp,
                    "is_conf_tourney": is_conf_tourney,
                    "is_conf_tourney_final": is_conf_tourney_final,
                    "season_type": 2,
                })

    teams_df = pd.DataFrame(
        list(teams_meta.values()),
        columns=["team", "conference", "is_auto_bid", "power_opponents_declined"],
    ).sort_values("team").reset_index(drop=True)
    games_df = pd.DataFrame(game_rows)
    if not games_df.empty:
        teams_df.to_csv("teams.csv", index=False)
        games_df.to_csv("games.csv", index=False)
    return teams_df, games_df


def fetch_espn_basketball_season(season_start_year: int):
    start_date, end_date = basketball_season_date_bounds(season_start_year)
    return fetch_espn_season_games(
        start_date=start_date.strftime("%Y%m%d"),
        end_date=end_date.strftime("%Y%m%d"),
    )


def fetch_espn_remaining_schedule(
    season_start_year: int,
    today: Optional[datetime] = None,
) -> pd.DataFrame:
    season_year = int(season_start_year)
    today = today or datetime.now()
    basketball_season_date_bounds(season_year, today)
    season_end = datetime(season_year + 1, 4, 15)
    today = today.replace(hour=0, minute=0, second=0, microsecond=0)
    schedule_start = max(datetime(season_start_year, 11, 1), today)
    if schedule_start > season_end:
        return pd.DataFrame(
            columns=["date", "team", "opponent", "location", "is_conf", "is_conf_tourney"]
        )

    date_strings = [
        (schedule_start + timedelta(days=offset)).strftime("%Y%m%d")
        for offset in range((season_end - schedule_start).days + 1)
    ]

    def fetch_scoreboard(date_str: str):
        try:
            response = requests.get(
                ESPN_SCOREBOARD_URL,
                params={"dates": date_str, "groups": "50", "limit": "500"},
                timeout=15,
            )
            response.raise_for_status()
            return date_str, response.json()
        except requests.RequestException as exc:
            raise RuntimeError(f"ESPN schedule request failed for {date_str}: {exc}") from exc

    scheduled_games = {}
    with ThreadPoolExecutor(max_workers=min(6, len(date_strings))) as executor:
        for date_str, data in executor.map(fetch_scoreboard, date_strings):
            for event in data.get("events", []):
                if str(event.get("season", {}).get("type", "")) != "2":
                    continue
                competitions = event.get("competitions", [])
                if not competitions:
                    continue
                competition = competitions[0]
                if competition.get("status", {}).get("type", {}).get("completed", False):
                    continue

                competitors = competition.get("competitors", [])
                if len(competitors) != 2:
                    continue
                conference_ids = [
                    str(item.get("team", {}).get("conferenceId", ""))
                    for item in competitors
                ]
                if not all(conf_id in ESPN_CONFERENCE_NAMES for conf_id in conference_ids):
                    continue

                home_index = next(
                    (i for i, item in enumerate(competitors) if item.get("homeAway") == "home"),
                    0,
                )
                away_index = 1 - home_index
                home_team = competitors[home_index].get("team", {})
                away_team = competitors[away_index].get("team", {})
                home_name = home_team.get("location") or home_team.get("displayName")
                away_name = away_team.get("location") or away_team.get("displayName")
                if not home_name or not away_name:
                    continue

                conference_game = bool(competition.get("conferenceCompetition", False))
                headlines = [
                    note.get("headline", "")
                    for note in competition.get("notes", [])
                ]
                notes = " ".join(headlines).lower()
                tournament_game = conference_game and any(
                    marker in notes for marker in ("championship", "tournament", "playoff")
                )
                neutral_site = bool(competition.get("neutralSite", False))
                location = "N" if neutral_site or tournament_game else "H"
                scheduled_games[str(event.get("id", f"{date_str}:{home_name}:{away_name}"))] = {
                    "date": date_str,
                    "team": home_name,
                    "opponent": away_name,
                    "location": location,
                    "is_conf": conference_game,
                    "is_conf_tourney": tournament_game,
                }

    return pd.DataFrame(
        scheduled_games.values(),
        columns=["date", "team", "opponent", "location", "is_conf", "is_conf_tourney"],
    ).sort_values("date").reset_index(drop=True)


# ==========================================
# 3. COLLEY MATRIX SOLVER (100% PUBLIC MATH)
# ==========================================
def compute_colley_ratings(teams_df: pd.DataFrame, games_df: pd.DataFrame) -> pd.DataFrame:
    teams = sorted(teams_df["team"].unique())
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    C = np.eye(n) * 2.0
    b = np.ones(n)

    valid_games = games_df[games_df["team"].isin(idx) & games_df["opponent"].isin(idx)]
    for _, row in valid_games.iterrows():
        i, j = idx[row["team"]], idx[row["opponent"]]
        C[i, i] += 1.0
        C[i, j] -= 1.0
        b[i] += 0.5 if bool(row["won"]) else -0.5

    ratings = np.linalg.solve(C, b)
    rating_map = dict(zip(teams, ratings))

    sos_map = {}
    for t in teams:
        opps = valid_games.loc[valid_games["team"] == t, "opponent"]
        sos_map[t] = float(np.mean([rating_map[o] for o in opps])) if len(opps) > 0 else 0.5

    res = teams_df.copy()
    res["colley_rating"] = res["team"].map(rating_map)
    res["colley_sos"] = res["team"].map(sos_map)
    res["colley_rank"] = res["colley_rating"].rank(ascending=False, method="min").astype(int)
    return res

# ==========================================
# 4. SELECTION ENGINE & INTRA-CONF SHIFT
# ==========================================
def run_selection_model(
    teams_df: pd.DataFrame,
    games_df: pd.DataFrame,
    season_start_year: Optional[int] = None,
) -> pd.DataFrame:
    if season_start_year is None:
        season_start_year = season_start_year_from_games(games_df)
    target_field_size = field_size_for_season(season_start_year)
    df = compute_colley_ratings(teams_df, games_df)
    rank_lookup = dict(zip(df["team"], df["colley_rank"]))
    valid_games = games_df[games_df["team"].isin(rank_lookup) & games_df["opponent"].isin(rank_lookup)]
    if "is_conf_tourney" not in valid_games:
        valid_games = valid_games.copy()
        valid_games["is_conf_tourney"] = False
    tournament_teams = set(
        valid_games.loc[valid_games["is_conf_tourney"].map(is_enabled), "team"]
    )
    team_conference = dict(zip(df["team"], df["conference"]))
    tournament_conferences = {
        team_conference[team] for team in tournament_teams if team in team_conference
    }

    records = []
    for _, t_row in df.iterrows():
        team = t_row["team"]
        t_games = valid_games[valid_games["team"] == team]

        raw_pts = 0.0
        non_con_road_neutral_top100 = 0
        reg_conf_wins = 0
        reg_conf_losses = 0

        for _, g in t_games.iterrows():
            opp_rank = rank_lookup[g["opponent"]]
            tier = get_tier(opp_rank)
            won = bool(g["won"])
            outcome = "W" if won else "L"
            loc = g["location"]

            raw_pts += POINT_LEDGER[tier][outcome][loc]

            if not bool(g["is_conf"]) and loc in ("A", "N") and opp_rank <= 100:
                non_con_road_neutral_top100 += 1

            if bool(g["is_conf"]) and not bool(g["is_conf_tourney"]):
                if won:
                    reg_conf_wins += 1
                else:
                    reg_conf_losses += 1

        total_wins = int(t_games["won"].astype(bool).sum())
        total_losses = int((~t_games["won"].astype(bool)).sum())
        conf_games = reg_conf_wins + reg_conf_losses
        conf_win_pct = (reg_conf_wins / conf_games) if conf_games > 0 else 0.0

        passes_conf_gate = conf_games == 0 or conf_win_pct > 0.500
        power_opponents_declined = is_enabled(t_row.get("power_opponents_declined", False))
        shutout_exempt = (
            total_wins >= 28
            and reg_conf_losses <= 1
            and power_opponents_declined
        )
        passes_road_gate = (non_con_road_neutral_top100 >= 2) or shutout_exempt
        is_eligible_at_large = passes_conf_gate and passes_road_gate

        sos_mult = 1.0 + (t_row["colley_sos"] * 0.15)
        regular_season_complete = t_row["conference"] in tournament_conferences
        dom_bonus = get_dominance_bonus(reg_conf_losses) if regular_season_complete else 0.0
        selection_score = (raw_pts * sos_mult) + dom_bonus

        records.append({
            "Team": team,
            "Conference": str(t_row["conference"]),
            "Auto_Bid": bool(t_row["is_auto_bid"]),
            "Power_Opponents_Declined": power_opponents_declined,
            "Regular_Season_Complete": regular_season_complete,
            "Record": f"{total_wins}-{total_losses}",
            "Conf_Record": f"{reg_conf_wins}-{reg_conf_losses}",
            "Colley_Rating": float(t_row["colley_rating"]),
            "Colley_Rank": int(t_row["colley_rank"]),
            "Colley_SOS": round(t_row["colley_sos"], 3),
            "Raw_Points": round(raw_pts, 2),
            "Dom_Bonus": dom_bonus,
            "Selection_Score": round(selection_score, 2),
            "Passes_Conf_Gate": passes_conf_gate,
            "Passes_Road_Gate": passes_road_gate,
            "At_Large_Eligible": is_eligible_at_large,
        })

    board = pd.DataFrame(records).sort_values("Selection_Score", ascending=False).reset_index(drop=True)
    board["Overall_Rank"] = board.index + 1

    board["Auto_Bid_Status"] = "Not selected"
    board.loc[board["Auto_Bid"], "Auto_Bid_Status"] = "Confirmed"
    confirmed_conferences = set(board.loc[board["Auto_Bid"], "Conference"])
    unconfirmed_teams = board[~board["Conference"].isin(confirmed_conferences)]
    projected_leaders = unconfirmed_teams.groupby("Conference", sort=False).head(1)["Team"]
    projected_mask = board["Team"].isin(projected_leaders)
    board.loc[projected_mask, "Auto_Bid"] = True
    board.loc[projected_mask, "Auto_Bid_Status"] = "Projected"

    auto_df = board[board["Auto_Bid"]].copy()
    first_four_auto_bids = set(
        auto_df.nsmallest(4, "Selection_Score")["Team"]
    )
    board["First_Four"] = board["Team"].isin(first_four_auto_bids)
    num_at_large = max(0, target_field_size - len(auto_df))
    at_large_df = board[(~board["Auto_Bid"]) & (board["At_Large_Eligible"])].head(num_at_large).copy()

    field = pd.concat([auto_df, at_large_df]).sort_values("Selection_Score", ascending=False).reset_index(drop=True)
    field["True_Seed_Order"] = field.index + 1
    field["Seed_Line"] = np.ceil(field["True_Seed_Order"] / 4.0).astype(int)
    if target_field_size == 68:
        field["Seed_Line"] = field["Seed_Line"].clip(upper=16)
    field = apply_intra_conference_shift(field)

    board["Status"] = "Out"
    board.loc[board["Auto_Bid_Status"] == "Confirmed", "Status"] = "Auto-Bid"
    board.loc[board["Auto_Bid_Status"] == "Projected", "Status"] = "Projected Auto-Bid"
    board.loc[board["Team"].isin(at_large_df["Team"]), "Status"] = "At-Large"
    board.loc[(~board["Auto_Bid"]) & (~board["Passes_Conf_Gate"]), "Status"] = "DQ (<= .500 Conf)"

    seed_map = dict(zip(field["Team"], field["Seed_Line"]))
    region_map = dict(zip(field["Team"], field["Region"]))
    board["Projected_Seed"] = board["Team"].map(seed_map)
    board["Region"] = board["Team"].map(region_map)

    return board


def simulate_season_projection(
    board: pd.DataFrame,
    games_df: pd.DataFrame,
    scheduled_games: pd.DataFrame,
    season_start_year: int,
    simulations: int = 300,
) -> pd.DataFrame:
    if scheduled_games.empty:
        raise ValueError("No remaining scheduled Division I games were found for this season.")
    if simulations < 1:
        raise ValueError("Run at least one season simulation.")

    teams = board["Team"].tolist()
    team_index = {team: index for index, team in enumerate(teams)}
    team_count = len(teams)
    ratings = board.set_index("Team")["Colley_Rating"].to_dict()
    ranks = board.set_index("Team")["Colley_Rank"].to_dict()
    conferences = board["Conference"].tolist()
    conference_indexes = {}
    for index, conference in enumerate(conferences):
        conference_indexes.setdefault(conference, []).append(index)

    actual = games_df[
        games_df["team"].isin(team_index) & games_df["opponent"].isin(team_index)
    ].copy()
    if "is_conf" not in actual:
        actual["is_conf"] = False
    if "is_conf_tourney" not in actual:
        actual["is_conf_tourney"] = False
    actual["won"] = actual["won"].map(is_enabled)
    actual["is_conf"] = actual["is_conf"].map(is_enabled)
    actual["is_conf_tourney"] = actual["is_conf_tourney"].map(is_enabled)

    current_wins = np.zeros(team_count, dtype=float)
    current_conf_wins = np.zeros(team_count, dtype=float)
    current_conf_losses = np.zeros(team_count, dtype=float)
    current_road_top100 = np.zeros(team_count, dtype=float)
    current_raw_points = board["Raw_Points"].to_numpy(dtype=float)

    for row in actual.itertuples():
        team_idx = team_index[row.team]
        opponent_rank = ranks[row.opponent]
        if row.won:
            current_wins[team_idx] += 1
        if row.is_conf and not row.is_conf_tourney:
            if row.won:
                current_conf_wins[team_idx] += 1
            else:
                current_conf_losses[team_idx] += 1
        if (
            not row.is_conf
            and row.location in ("A", "N")
            and opponent_rank <= 100
        ):
            current_road_top100[team_idx] += 1

    sched = scheduled_games[
        scheduled_games["team"].isin(team_index)
        & scheduled_games["opponent"].isin(team_index)
    ].copy()
    if sched.empty:
        raise ValueError("No remaining scheduled games match the Division I roster.")
    if "is_conf" not in sched:
        sched["is_conf"] = False
    if "is_conf_tourney" not in sched:
        sched["is_conf_tourney"] = False
    sched["is_conf"] = sched["is_conf"].map(is_enabled)
    sched["is_conf_tourney"] = sched["is_conf_tourney"].map(is_enabled)

    game_count = len(sched)
    win_deltas = np.zeros((game_count, team_count), dtype=float)
    conf_win_deltas = np.zeros((game_count, team_count), dtype=float)
    raw_point_deltas = np.zeros((game_count, team_count), dtype=float)
    future_wins_base = np.zeros(team_count, dtype=float)
    future_conf_wins_base = np.zeros(team_count, dtype=float)
    future_conf_game_count = np.zeros(team_count, dtype=float)
    future_road_top100 = np.zeros(team_count, dtype=float)
    future_raw_points_base = np.zeros(team_count, dtype=float)
    home_indices = []
    away_indices = []
    win_probabilities = []

    for game_number, game in enumerate(sched.itertuples()):
        home_idx = team_index[game.team]
        away_idx = team_index[game.opponent]
        home_indices.append(home_idx)
        away_indices.append(away_idx)

        location = game.location if game.location in ("H", "A", "N") else "N"
        away_location = "N" if location == "N" else {"H": "A", "A": "H"}[location]
        home_tier = get_tier(ranks[game.team])
        away_tier = get_tier(ranks[game.opponent])

        home_win_points = POINT_LEDGER[away_tier]["W"][location]
        home_loss_points = POINT_LEDGER[away_tier]["L"][location]
        away_win_points = POINT_LEDGER[home_tier]["W"][away_location]
        away_loss_points = POINT_LEDGER[home_tier]["L"][away_location]
        future_raw_points_base[home_idx] += home_loss_points
        future_raw_points_base[away_idx] += away_win_points
        raw_point_deltas[game_number, home_idx] += home_win_points - home_loss_points
        raw_point_deltas[game_number, away_idx] += away_loss_points - away_win_points

        future_wins_base[away_idx] += 1
        win_deltas[game_number, home_idx] += 1
        win_deltas[game_number, away_idx] -= 1

        if game.is_conf and not game.is_conf_tourney:
            future_conf_game_count[home_idx] += 1
            future_conf_game_count[away_idx] += 1
            future_conf_wins_base[away_idx] += 1
            conf_win_deltas[game_number, home_idx] += 1
            conf_win_deltas[game_number, away_idx] -= 1

        if not game.is_conf:
            if location in ("A", "N") and ranks[game.opponent] <= 100:
                future_road_top100[home_idx] += 1
            if away_location in ("A", "N") and ranks[game.team] <= 100:
                future_road_top100[away_idx] += 1

        venue_adjustment = 0.25 if location == "H" else (-0.25 if location == "A" else 0.0)
        logit = 10.0 * (ratings[game.team] - ratings[game.opponent]) + venue_adjustment
        win_probabilities.append(float(np.clip(1.0 / (1.0 + np.exp(-logit)), 0.05, 0.95)))

    rng = np.random.default_rng(42)
    outcomes = (
        rng.random((simulations, game_count)) < np.asarray(win_probabilities)
    ).astype(float)
    projected_wins = current_wins + future_wins_base + outcomes @ win_deltas
    projected_conf_wins = current_conf_wins + future_conf_wins_base + outcomes @ conf_win_deltas
    projected_conf_losses = (
        current_conf_losses
        + future_conf_game_count
        - future_conf_wins_base
        - outcomes @ conf_win_deltas
    )
    projected_raw_points = (
        current_raw_points
        + future_raw_points_base
        + outcomes @ raw_point_deltas
    )

    conference_games = (
        current_conf_wins + current_conf_losses + future_conf_game_count
    )
    conference_gate = np.where(
        conference_games > 0,
        projected_conf_wins > projected_conf_losses,
        True,
    )
    road_gate_count = current_road_top100 + future_road_top100
    power_opponents_declined = board.get(
        "Power_Opponents_Declined",
        pd.Series(False, index=board.index),
    ).map(is_enabled).to_numpy()
    eligible = (
        conference_gate
        & (
            (road_gate_count >= 2)
            | (
                (projected_wins >= 28)
                & (projected_conf_losses <= 1)
                & power_opponents_declined[None, :]
            )
        )
    )

    loss_counts = projected_conf_losses
    dominance_bonus = np.select(
        [loss_counts <= 1, loss_counts == 2, loss_counts == 3],
        [12.0, 8.0, 4.0],
        default=0.0,
    )
    has_conference_games = conference_games > 0
    dominance_bonus[:, ~has_conference_games] = 0.0
    sos_multiplier = 1.0 + board["Colley_SOS"].to_numpy(dtype=float) * 0.15
    projected_scores = projected_raw_points * sos_multiplier[None, :] + dominance_bonus

    confirmed_auto = board["Status"].eq("Auto-Bid").to_numpy()
    field_size = field_size_for_season(season_start_year)
    field_counts = np.zeros(team_count, dtype=float)
    auto_bid_counts = np.zeros(team_count, dtype=float)
    for simulation in range(simulations):
        selected_auto = confirmed_auto.copy()
        auto_bid_counts += confirmed_auto
        for conference, indexes in conference_indexes.items():
            if not any(confirmed_auto[index] for index in indexes):
                projected_champion = indexes[
                    int(np.argmax(projected_scores[simulation, indexes]))
                ]
                selected_auto[projected_champion] = True
                auto_bid_counts[projected_champion] += 1

        selected = selected_auto.copy()
        available_slots = max(0, field_size - int(selected_auto.sum()))
        candidates = np.flatnonzero(eligible[simulation] & ~selected_auto)
        if available_slots and len(candidates):
            ranked_candidates = candidates[
                np.argsort(projected_scores[simulation, candidates])[::-1]
            ]
            selected[ranked_candidates[:available_slots]] = True
        field_counts += selected

    result = board.copy()
    wins_10 = np.percentile(projected_wins, 10, axis=0)
    wins_90 = np.percentile(projected_wins, 90, axis=0)
    score_10 = np.percentile(projected_scores, 10, axis=0)
    score_90 = np.percentile(projected_scores, 90, axis=0)
    total_scheduled = np.zeros(team_count, dtype=float)
    np.add.at(total_scheduled, home_indices, 1)
    np.add.at(total_scheduled, away_indices, 1)
    actual_games_by_team = actual.groupby("team").size().reindex(teams, fill_value=0).to_numpy()
    projected_losses = actual_games_by_team[None, :] + total_scheduled[None, :] - projected_wins
    field_probability = field_counts / simulations
    auto_bid_probability = auto_bid_counts / simulations
    result["Projection_Record"] = [
        f"{wins:.1f}-{losses:.1f}"
        for wins, losses in zip(projected_wins.mean(axis=0), projected_losses.mean(axis=0))
    ]
    result["Projection_Win_Range"] = [
        f"{int(np.floor(low))}-{int(np.ceil(high))}"
        for low, high in zip(wins_10, wins_90)
    ]
    result["Projection_Selection_Score"] = projected_scores.mean(axis=0).round(2)
    result["Projection_Rank"] = result["Projection_Selection_Score"].rank(
        ascending=False,
        method="min",
    ).astype(int)
    result["Projection_Score_Range"] = [
        f"{low:.1f}-{high:.1f}"
        for low, high in zip(score_10, score_90)
    ]
    result["Field_Probability"] = (field_probability * 100).round(1)
    result["Auto_Bid_Probability"] = (auto_bid_probability * 100).round(1)
    result["Projection_Status"] = np.select(
        [field_probability >= 0.75, field_probability >= 0.25],
        ["Likely in field", "Bubble"],
        default="Long shot",
    )
    return result.sort_values(
        ["Field_Probability", "Projection_Selection_Score"],
        ascending=[False, False],
    ).reset_index(drop=True)


def build_conference_summary(board: pd.DataFrame) -> pd.DataFrame:
    projected = board[board["Projected_Seed"].notna()].copy()
    summaries = []
    for conference in sorted(board["Conference"].dropna().unique()):
        teams = projected[projected["Conference"] == conference].sort_values(
            ["Projected_Seed", "Selection_Score"],
            ascending=[True, False],
        )
        summaries.append({
            "Conference": conference,
            "Projected_Teams": len(teams),
            "Confirmed_Auto_Bids": int((teams["Status"] == "Auto-Bid").sum()),
            "Projected_Auto_Bids": int((teams["Status"] == "Projected Auto-Bid").sum()),
            "At_Large": int((teams["Status"] == "At-Large").sum()),
            "Best_Seed": f"#{int(teams['Projected_Seed'].min())}" if not teams.empty else "—",
            "Teams": ", ".join(
                f"{row.Team} (#{int(row.Projected_Seed)})"
                for row in teams.itertuples()
            ) or "—",
        })
    return pd.DataFrame(summaries).sort_values(
        ["Projected_Teams", "Conference"],
        ascending=[False, True],
    ).reset_index(drop=True)


def apply_intra_conference_shift(field: pd.DataFrame) -> pd.DataFrame:
    regions = ["East", "West", "South", "Midwest"]
    assigned_regions = []
    for i in range(len(field)):
        row_block = i // 4
        pos = i % 4
        assigned_regions.append(regions[pos] if row_block % 2 == 0 else regions[3 - pos])

    field["Region"] = assigned_regions

    pod_pairs = [(1, 16, 8, 9), (4, 13, 5, 12), (3, 14, 6, 11), (2, 15, 7, 10)]
    for reg in regions:
        reg_mask = field["Region"] == reg
        for pod in pod_pairs:
            pod_teams = field[reg_mask & field["Seed_Line"].isin(pod)]
            if pod_teams["Conference"].nunique() < len(pod_teams):
                dups = pod_teams[pod_teams.duplicated("Conference", keep="first")]
                for idx_dup in dups.index:
                    curr_seed = field.loc[idx_dup, "Seed_Line"]
                    target_seed = curr_seed + 1 if curr_seed < 16 else curr_seed - 1
                    swap_candidates = field[(field["Region"] != reg) & (field["Seed_Line"] == target_seed)]
                    if not swap_candidates.empty:
                        swap_idx = swap_candidates.index[0]
                        field.loc[idx_dup, "Seed_Line"], field.loc[swap_idx, "Seed_Line"] = (
                            field.loc[swap_idx, "Seed_Line"],
                            field.loc[idx_dup, "Seed_Line"],
                        )
                        field.loc[idx_dup, "Region"], field.loc[swap_idx, "Region"] = (
                            field.loc[swap_idx, "Region"],
                            field.loc[idx_dup, "Region"],
                        )
    return field

# ==========================================
# 5. LOAD LOCAL CSVs OR FALLBACK TO SAMPLE
# ==========================================
def load_or_init_data():
    global LEGACY_DATA_WARNING
    if os.path.exists("teams.csv") and os.path.exists("games.csv"):
        teams_df = pd.read_csv("teams.csv")
        teams_df["conference"] = teams_df["conference"].map(get_conference_name)
        teams_df = teams_df[teams_df["conference"].isin(DIVISION_I_CONFERENCES)].copy()
        teams_df = teams_df.drop_duplicates("team", keep="last").reset_index(drop=True)
        if "power_opponents_declined" not in teams_df:
            teams_df["power_opponents_declined"] = False

        games_df = pd.read_csv("games.csv")
        LEGACY_DATA_WARNING = "season_type" not in games_df.columns
        if not LEGACY_DATA_WARNING:
            games_df = games_df[games_df["season_type"].astype(str) == "2"].copy()
        division_i_teams = set(teams_df["team"])
        games_df = games_df[
            games_df["team"].isin(division_i_teams)
            & games_df["opponent"].isin(division_i_teams)
        ].copy()

        if not games_df.empty:
            season_years = games_df["date"].map(basketball_season_year)
            latest_season_year = season_years.max()
            games_df = games_df.loc[season_years == latest_season_year].copy()

        if "is_conf_tourney" not in games_df:
            games_df["is_conf_tourney"] = False
        games_df.loc[games_df["is_conf_tourney"].map(is_enabled), "location"] = "N"
        return teams_df, games_df.reset_index(drop=True)
    LEGACY_DATA_WARNING = False
    return generate_sample_season()

def generate_sample_season():
    rng = np.random.default_rng(42)
    confs = ["ACC", "Big 12", "Big Ten", "SEC", "Big East", "WCC", "MWC", "A-10", "MAC", "CUSA", "MVC", "SWAC"]
    teams_data = []
    for c_idx, conf in enumerate(confs):
        strength_base = max(0.35, 0.82 - c_idx * 0.04)
        for t_num in range(1, 9):
            t_name = f"{conf}_Team_{t_num}"
            strength = strength_base - (t_num - 1) * 0.045
            teams_data.append({
                "team": t_name,
                "conference": conf,
                "strength": strength,
                "is_auto_bid": (t_num == 1),
                "power_opponents_declined": False,
            })
    teams_df = pd.DataFrame(teams_data)

    games = []
    team_list = teams_df.to_dict("records")
    for i, t1 in enumerate(team_list):
        opps = rng.choice([x for x in range(len(team_list)) if x != i], size=5, replace=False)
        for j in opps:
            t2 = team_list[j]
            loc = rng.choice(["H", "A", "N"], p=[0.5, 0.3, 0.2])
            p_win = 1 / (1 + np.exp(-(t1["strength"] - t2["strength"]) * 6))
            won = bool(rng.random() < p_win)
            opp_loc = {"H": "A", "A": "H", "N": "N"}[loc]
            games.append({"date": "20261115", "team": t1["team"], "opponent": t2["team"], "location": loc, "won": won, "is_conf": False, "is_conf_tourney": False})
            games.append({"date": "20261115", "team": t2["team"], "opponent": t1["team"], "location": opp_loc, "won": not won, "is_conf": False, "is_conf_tourney": False})

    for conf in confs:
        c_teams = [t for t in team_list if t["conference"] == conf]
        for i in range(len(c_teams)):
            for j in range(i + 1, len(c_teams)):
                for home_team, away_team in [(c_teams[i], c_teams[j]), (c_teams[j], c_teams[i])]:
                    p_win = 1 / (1 + np.exp(-(home_team["strength"] - away_team["strength"] + 0.05) * 6))
                    won = bool(rng.random() < p_win)
                    games.append({"date": "20270115", "team": home_team["team"], "opponent": away_team["team"], "location": "H", "won": won, "is_conf": True, "is_conf_tourney": False})
                    games.append({"date": "20270115", "team": away_team["team"], "opponent": home_team["team"], "location": "A", "won": not won, "is_conf": True, "is_conf_tourney": False})

    return teams_df[
        ["team", "conference", "is_auto_bid", "power_opponents_declined"]
    ], pd.DataFrame(games)

# ==========================================
# 6. PLOTLY DASH INTERACTIVE APPLICATION
# ==========================================
teams_df, games_df = load_or_init_data()
CURRENT_BOARD = run_selection_model(teams_df, games_df)
CURRENT_GAMES = games_df
CURRENT_CONFERENCE_SUMMARY = build_conference_summary(CURRENT_BOARD)
CURRENT_FIELD_SIZE = field_size_for_season(season_start_year_from_games(games_df))
CURRENT_SEASON_START_YEAR = season_start_year_from_games(games_df)
CURRENT_PROJECTION_BOARD = None
CURRENT_SCHEDULED_GAMES = pd.DataFrame()
CURRENT_PROJECTION_SEASON = None
SIMULATION_COUNT = 300
SEASON_OPTIONS = [
    {
        "label": f"{season_year}-{season_year + 1}",
        "value": season_year,
    }
    for season_year in range(CURRENT_SEASON_START_YEAR, 2009, -1)
]
INITIAL_STATUS = (
    "Legacy CSV detected: postseason games cannot be identified in this data. "
    "Fetch a season to rebuild the board with only regular-season and conference-tournament games."
    if LEGACY_DATA_WARNING
    else "Loaded local data."
)

APP_NAME = "SWISH: Schedule-Weighted Independent Selection & Seeding Hierarchy"
DATE_INPUT_STYLE = {
    "display": "block",
    "width": "100%",
    "height": "42px",
    "padding": "0 11px",
    "border": "1px solid #dfe5ee",
    "borderRadius": "8px",
    "backgroundColor": "#ffffff",
    "color": "#24334a",
    "fontSize": "13px",
    "boxSizing": "border-box",
}

app = Dash(__name__)
app.title = APP_NAME

app.layout = html.Div(
    className="app-shell",
    children=[
        html.Header(
            className="hero",
            children=[
                html.Div(
                    className="hero-copy",
                    children=[
                        html.Div(
                            children=[
                                html.P("COLLEGE BASKETBALL · SELECTION MODEL", className="eyebrow"),
                                html.H1("SWISH", className="hero-title"),
                                html.P(
                                    "Schedule-Weighted Independent Selection & Seeding Hierarchy",
                                    className="hero-subtitle",
                                ),
                                html.P(
                                    "A transparent, data-driven look at the road to the tournament.",
                                    className="hero-description",
                                ),
                            ]
                        ),
                    ],
                ),
                html.Div(
                    className="hero-note",
                    children=[
                        html.Span(className="live-dot"),
                        html.Span("SELECTION BOARD"),
                        html.Strong("SELECT A BASKETBALL SEASON"),
                    ],
                ),
            ],
        ),
        html.Main(
            className="main-content",
            children=[
                html.Section(
                    className="stats-grid",
                    children=[
                        html.Div(
                            className="stat-card",
                            children=[
                                html.Span("TEAMS TRACKED", className="stat-label"),
                                html.Strong(f"{len(CURRENT_BOARD):,}", id="teams-tracked-count", className="stat-value"),
                                html.Span("In the current dataset", className="stat-detail"),
                            ],
                        ),
                        html.Div(
                            className="stat-card",
                            children=[
                                html.Span("GAMES LOADED", className="stat-label"),
                                html.Strong(f"{len(CURRENT_GAMES) // 2:,}", id="games-loaded-count", className="stat-value"),
                                html.Span("Completed matchups", className="stat-detail"),
                            ],
                        ),
                        html.Div(
                            className="stat-card stat-card-accent",
                            children=[
                                html.Span("PROJECTED FIELD", className="stat-label"),
                                html.Strong(str(CURRENT_FIELD_SIZE), id="projected-field-count", className="stat-value"),
                                html.Span("Teams · four regions", className="stat-detail"),
                            ],
                        ),
                    ],
                ),
                html.Details(
                    className="conference-summary-panel",
                    open=False,
                    children=[
                        html.Summary(
                            className="conference-summary-heading",
                            children="Projected teams by conference",
                        ),
                        html.Div(
                            className="conference-summary-table-wrap",
                            children=[
                                html.Div(
                                    className="conference-summary-intro",
                                    children=[
                                        html.Div(
                                            [
                                                html.P("CONFERENCE BREAKDOWN", className="eyebrow"),
                                                html.P(
                                                    "See how each conference is represented in the projected tournament field.",
                                                    className="section-description",
                                                ),
                                            ]
                                        ),
                                        html.Span(
                                            "Counts include auto-bids and at-large selections.",
                                            className="conference-summary-note",
                                        ),
                                    ],
                                ),
                                dash_table.DataTable(
                            id="conference-summary-table",
                            columns=[
                                {"name": "Conference", "id": "Conference"},
                                {"name": "Teams in field", "id": "Projected_Teams", "type": "numeric"},
                                {"name": "Confirmed auto-bids", "id": "Confirmed_Auto_Bids", "type": "numeric"},
                                {"name": "Projected auto-bids", "id": "Projected_Auto_Bids", "type": "numeric"},
                                {"name": "At-large", "id": "At_Large", "type": "numeric"},
                                {"name": "Best seed", "id": "Best_Seed"},
                                {"name": "Projected teams", "id": "Teams"},
                            ],
                            data=CURRENT_CONFERENCE_SUMMARY.to_dict("records"),
                            sort_action="native",
                            sort_by=[{"column_id": "Projected_Teams", "direction": "desc"}],
                            page_action="native",
                            page_size=12,
                            style_table={"overflowX": "auto"},
                            style_cell={
                                "fontFamily": "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
                                "textAlign": "left",
                                "padding": "11px 14px",
                                "fontSize": "12px",
                                "border": "none",
                                "borderBottom": "1px solid #edf0f4",
                                "minWidth": "90px",
                                "whiteSpace": "normal",
                                "height": "auto",
                            },
                            style_header={
                                "backgroundColor": "#f6f8fb",
                                "color": "#687386",
                                "fontWeight": "700",
                                "fontSize": "10px",
                                "letterSpacing": "0.06em",
                                "textTransform": "uppercase",
                                "border": "none",
                                "borderBottom": "1px solid #e6eaf0",
                                "padding": "11px 14px",
                            },
                            style_data_conditional=[
                                {"if": {"row_index": "odd"}, "backgroundColor": "#fbfcfe"},
                                {"if": {"column_id": "Conference"}, "fontWeight": "700", "color": "#16243a"},
                                {"if": {"column_id": "Projected_Teams"}, "fontWeight": "700", "color": "#2864dc"},
                            ],
                                ),
                            ],
                        ),
                    ],
                ),
                html.Details(
                    className="methodology-panel",
                    children=[
                        html.Summary("How SWISH calculates the field"),
                        html.Div(
                            className="methodology-content",
                            children=[
                                html.P(
                                    "The model follows the SWISH selection rulebook: it ranks current-season "
                                    "Division I results with Colley ratings, then evaluates each game by opponent "
                                    "tier and venue. ESPN season type 2 regular-season and conference-tournament "
                                    "games are included; preseason and NCAA postseason games are excluded. "
                                    "Wins and losses are counted equally regardless of margin."
                                ),
                                html.Div(
                                    className="methodology-grid",
                                    children=[
                                        html.Div(
                                            children=[
                                                html.H3("Eligibility gates"),
                                                html.Ul(
                                                    [
                                                        html.Li(
                                                            "At-large teams must finish above .500 in regular-season "
                                                            "conference play and play at least two nonconference away "
                                                            "or neutral games against Colley top-100 opponents."
                                                        ),
                                                        html.Li(
                                                            "Exception: 28+ overall wins and no more than one "
                                                            "conference loss, only when power-conference opponents "
                                                            "declined a series. Set power_opponents_declined=True in teams.csv."
                                                        ),
                                                        html.Li(
                                                            "A team with a 0–0 conference record passes provisionally "
                                                            "until it plays a conference game."
                                                        ),
                                                    ]
                                                ),
                                            ]
                                        ),
                                        html.Div(
                                            children=[
                                                html.H3("Score and conference bonus"),
                                                html.P(
                                                    "Selection Score = (Raw Game Points × [1 + (Colley SOS × 0.15)]) "
                                                    "+ Conference Dominance Bonus. SOS is the average Colley rating "
                                                    "of Division I opponents."
                                                ),
                                                html.P(
                                                    "The bonus is +12 for 0–1 regular-season conference losses, "
                                                    "+8 for 2, +4 for 3, and 0 for 4+. It is applied once a "
                                                    "conference tournament has begun. Tournament games score as "
                                                    "neutral-site games but do not change the conference record."
                                                ),
                                                html.P(
                                                    "ESPN-detected conference tournament champions receive confirmed "
                                                    "auto-bids. When no final is detected, the conference's highest "
                                                    "Selection Score is shown as a projection. The number of "
                                                    "auto-bids follows the conferences detected for the season, so "
                                                    "the at-large count adjusts to the season's field size: 68 teams "
                                                    "through 2025-2026 and 76 teams from 2026-2027 onward."
                                                ),
                                                html.P(
                                                    "Teams are ordered by Selection Score for seeding. The four "
                                                    "lowest-scoring auto-bids are marked as First Four participants."
                                                ),
                                            ]
                                        ),
                                    ],
                                ),
                                html.H3("Raw game point ledger"),
                                html.Div(
                                    className="ledger-scroll",
                                    children=[
                                        html.Table(
                                            [
                                                html.Thead(
                                                    html.Tr(
                                                        [
                                                            html.Th("Tier / Colley rank"),
                                                            html.Th("Win H"),
                                                            html.Th("Win N"),
                                                            html.Th("Win A"),
                                                            html.Th("Loss H"),
                                                            html.Th("Loss N"),
                                                            html.Th("Loss A"),
                                                        ]
                                                    )
                                                ),
                                                html.Tbody(
                                                    [
                                                        html.Tr(
                                                            [
                                                                html.Th(f"Tier {tier} · {rank_range}"),
                                                                *[
                                                                    html.Td(f"{POINT_LEDGER[tier]['W'][loc]:g}")
                                                                    for loc in ("H", "N", "A")
                                                                ],
                                                                *[
                                                                    html.Td(f"{POINT_LEDGER[tier]['L'][loc]:g}")
                                                                    for loc in ("H", "N", "A")
                                                                ],
                                                            ]
                                                        )
                                                        for tier, rank_range in (
                                                            (1, "1–25"),
                                                            (2, "26–60"),
                                                            (3, "61–120"),
                                                            (4, "121–200"),
                                                            (5, "201+"),
                                                        )
                                                    ]
                                                ),
                                            ]
                                        )
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
                html.Section(
                    className="board-panel",
                    children=[
                        html.Div(
                            className="section-heading",
                            children=[
                                html.Div(
                                    children=[
                                        html.P("THE BRACKET PICTURE", className="eyebrow"),
                                        html.H2("Selection board"),
                                        html.P(
                                            "Rankings, tournament outlook, and the numbers behind each team's position.",
                                            className="section-description",
                                        ),
                                        html.Div(
                                            className="board-key",
                                            children=[
                                                html.Span([html.I(), "Confirmed auto-bid"]),
                                                html.Span([html.I(), "Projected auto-bid"]),
                                                html.Span([html.I(), "At-large"]),
                                            ],
                                        ),
                                    ]
                                ),
                                html.Div(
                                    className="method-chip",
                                    children=["COLLEY RATINGS", html.Span("＋"), "SCHEDULE-WEIGHTED SCORE"],
                                ),
                            ],
                        ),
                        html.Div(
                            className="filters",
                            children=[
                                html.Div(
                                    className="filter-field filter-field-view",
                                    children=[
                                        html.Label("BOARD VIEW", htmlFor="board-view"),
                                        dcc.RadioItems(
                                            id="board-view",
                                            options=[
                                                {"label": "Actual", "value": "ACTUAL"},
                                                {"label": "Projected", "value": "PROJECTED"},
                                            ],
                                            value="ACTUAL",
                                            inline=True,
                                            className="board-view-toggle",
                                        ),
                                        html.Small(
                                            "300 simulations use current Colley ratings and venue; brackets and game scores are not modeled. Ranges show the 10th–90th percentile.",
                                            className="filter-help",
                                        ),
                                    ],
                                ),
                                html.Div(
                                    className="filter-field filter-field-wide",
                                    children=[
                                        html.Label("VIEW TEAMS", htmlFor="status-filter"),
                                        dcc.Dropdown(
                                            id="status-filter",
                                            options=[
                                                {"label": "All Teams", "value": "ALL"},
                                                {"label": "Projected Tournament Field", "value": "FIELD"},
                                                {"label": "All Auto-Bids", "value": "AUTO_BIDS"},
                                                {"label": "Confirmed Auto-Bids", "value": "Auto-Bid"},
                                                {"label": "Projected Auto-Bids", "value": "Projected Auto-Bid"},
                                                {"label": "At-Large Qualifiers", "value": "At-Large"},
                                                {"label": "Disqualified (<= .500 Conf)", "value": "DQ (<= .500 Conf)"},
                                                {"label": "Likely in Field (Projection)", "value": "Likely in field"},
                                                {"label": "Bubble (Projection)", "value": "Bubble"},
                                                {"label": "Long Shot (Projection)", "value": "Long shot"},
                                            ],
                                            value="ALL",
                                            clearable=False,
                                        ),
                                    ],
                                ),
                                html.Div(
                                    className="filter-field",
                                    children=[
                                        html.Label("CONFERENCE", htmlFor="conf-filter"),
                                        dcc.Dropdown(
                                            id="conf-filter",
                                            options=[{"label": "All Conferences", "value": "ALL"}]
                                            + [{"label": c, "value": c} for c in sorted(CURRENT_BOARD["Conference"].unique())],
                                            value="ALL",
                                            clearable=False,
                                        ),
                                    ],
                                ),
                                html.Div(
                                    className="filter-field filter-field-season",
                                    children=[
                                        html.Label("BASKETBALL SEASON", htmlFor="season-select"),
                                        dcc.Dropdown(
                                            id="season-select",
                                            options=SEASON_OPTIONS,
                                            value=CURRENT_SEASON_START_YEAR,
                                            clearable=False,
                                            searchable=False,
                                        ),
                                        html.Small(
                                            "Actual game dates are reported after fetching.",
                                            className="filter-help",
                                        ),
                                    ],
                                ),
                                html.Button(
                                    ["↻", " Fetch selected season"],
                                    id="fetch-btn",
                                    n_clicks=0,
                                    className="fetch-button",
                                ),
                            ],
                        ),
                        html.Div(
                            className="board-meta",
                            children=[
                                html.Span("MODEL OUTPUT", className="board-meta-label"),
                                html.Span(id="fetch-status", children=INITIAL_STATUS),
                            ],
                        ),
                        dash_table.DataTable(
                            id="leaderboard-table",
                            columns=[{"name": col.replace("_", " "), "id": col} for col in [
                                "Overall_Rank", "Projected_Seed", "Region", "Status", "Team", "Conference",
                                "Record", "Conf_Record", "Selection_Score", "Raw_Points", "Dom_Bonus",
                                "First_Four", "Colley_Rank", "Colley_SOS", "Passes_Conf_Gate", "Passes_Road_Gate"
                            ]],
                            data=CURRENT_BOARD.to_dict("records"),
                            sort_action="native",
                            page_size=25,
                            style_table={"overflowX": "auto"},
                            style_cell={
                                "fontFamily": "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
                                "textAlign": "left",
                                "padding": "13px 15px",
                                "fontSize": "13px",
                                "border": "none",
                                "borderBottom": "1px solid #edf0f4",
                                "minWidth": "88px",
                                "width": "110px",
                                "maxWidth": "220px",
                                "whiteSpace": "normal",
                                "height": "auto",
                            },
                            style_header={
                                "backgroundColor": "#f6f8fb",
                                "color": "#687386",
                                "fontWeight": "700",
                                "fontSize": "10px",
                                "letterSpacing": "0.08em",
                                "textTransform": "uppercase",
                                "border": "none",
                                "borderBottom": "1px solid #e6eaf0",
                                "padding": "12px 15px",
                            },
                            style_data_conditional=[
                                {"if": {"row_index": "odd"}, "backgroundColor": "#fbfcfe"},
                                {"if": {"filter_query": '{Status} = "Auto-Bid"'}, "backgroundColor": "#eaf3ff"},
                                {"if": {"filter_query": '{Status} = "Projected Auto-Bid"'}, "backgroundColor": "#fff7e6"},
                                {"if": {"filter_query": '{Status} = "At-Large"'}, "backgroundColor": "#ecf8f1"},
                                {"if": {"filter_query": '{Status} = "DQ (<= .500 Conf)"'}, "backgroundColor": "#fff3f1"},
                                {"if": {"column_id": "Team"}, "fontWeight": "700", "color": "#16243a"},
                                {"if": {"column_id": "Overall_Rank"}, "fontWeight": "700", "color": "#53627a"},
                            ],
                            page_action="native",
                            page_current=0,
                            sort_by=[{"column_id": "Overall_Rank", "direction": "asc"}],
                        ),
                    ],
                ),
                html.Footer(
                    "SWISH · Transparent selection. Schedule-weighted perspective.",
                    className="app-footer",
                ),
            ],
        ),
    ],
)

@app.callback(
    Output("leaderboard-table", "data"),
    Output("leaderboard-table", "columns"),
    Output("leaderboard-table", "sort_by"),
    Output("conference-summary-table", "data"),
    Output("conf-filter", "options"),
    Output("fetch-status", "children"),
    Output("teams-tracked-count", "children"),
    Output("games-loaded-count", "children"),
    Output("projected-field-count", "children"),
    Input("status-filter", "value"),
    Input("conf-filter", "value"),
    Input("fetch-btn", "n_clicks"),
    Input("board-view", "value"),
    State("season-select", "value"),
)
def update_dashboard(status_val, conf_val, n_clicks, board_view, season_start_year):
    global CURRENT_BOARD, CURRENT_GAMES, CURRENT_CONFERENCE_SUMMARY
    global CURRENT_FIELD_SIZE, CURRENT_SEASON_START_YEAR, CURRENT_PROJECTION_BOARD
    global CURRENT_SCHEDULED_GAMES, CURRENT_PROJECTION_SEASON, LEGACY_DATA_WARNING
    status_msg = INITIAL_STATUS if LEGACY_DATA_WARNING else "Loaded local data."
    season_year = int(season_start_year)
    season_label = f"{season_year}-{season_year + 1}"

    if ctx.triggered_id == "fetch-btn" and n_clicks and n_clicks > 0:
        try:
            t_df, g_df = fetch_espn_basketball_season(season_year)
        except (ValueError, RuntimeError) as exc:
            status_msg = f"Fetch failed: {exc}"
        else:
            if not g_df.empty:
                CURRENT_BOARD = run_selection_model(t_df, g_df, season_year)
                CURRENT_GAMES = g_df
                CURRENT_CONFERENCE_SUMMARY = build_conference_summary(CURRENT_BOARD)
                CURRENT_FIELD_SIZE = field_size_for_season(season_year)
                CURRENT_SEASON_START_YEAR = season_year
                CURRENT_PROJECTION_BOARD = None
                CURRENT_SCHEDULED_GAMES = pd.DataFrame()
                CURRENT_PROJECTION_SEASON = None
                LEGACY_DATA_WARNING = False
                confirmed_bids = int(t_df["is_auto_bid"].astype(bool).sum())
                game_dates = pd.to_datetime(g_df["date"], format="%Y%m%d")
                status_msg = (
                    f"Season {season_label}: fetched {len(g_df)//2} completed games across {len(t_df)} teams, "
                    f"from {game_dates.min():%b %d, %Y} through {game_dates.max():%b %d, %Y}. "
                    f"Detected {confirmed_bids} conference-tournament final winners "
                    f"(saved to teams.csv & games.csv)."
                )
            else:
                status_msg = f"No completed regular-season or conference-tournament games found for {season_label}."

    if board_view == "PROJECTED" and (
        CURRENT_PROJECTION_SEASON != season_year
        or ctx.triggered_id == "fetch-btn"
    ):
        try:
            if CURRENT_SEASON_START_YEAR != season_year or LEGACY_DATA_WARNING:
                t_df, g_df = fetch_espn_basketball_season(season_year)
                if g_df.empty:
                    raise RuntimeError(f"No completed games were found for season {season_label}.")
                CURRENT_BOARD = run_selection_model(t_df, g_df, season_year)
                CURRENT_GAMES = g_df
                CURRENT_CONFERENCE_SUMMARY = build_conference_summary(CURRENT_BOARD)
                CURRENT_FIELD_SIZE = field_size_for_season(season_year)
                CURRENT_SEASON_START_YEAR = season_year
                LEGACY_DATA_WARNING = False
            CURRENT_SCHEDULED_GAMES = fetch_espn_remaining_schedule(season_year)
            CURRENT_PROJECTION_BOARD = simulate_season_projection(
                CURRENT_BOARD,
                CURRENT_GAMES,
                CURRENT_SCHEDULED_GAMES,
                season_year,
                SIMULATION_COUNT,
            )
            CURRENT_PROJECTION_SEASON = season_year
            status_msg = (
                f"Season {season_label}: simulated {len(CURRENT_SCHEDULED_GAMES)} remaining games "
                f"across {SIMULATION_COUNT} season runs. Current Colley ratings, opponent tiers, SOS, and venue "
                "are held fixed; conference tournament brackets and game scores are not projected."
            )
        except (ValueError, RuntimeError) as exc:
            CURRENT_PROJECTION_BOARD = None
            CURRENT_PROJECTION_SEASON = None
            status_msg = f"Projection unavailable: {exc}"

    showing_projection = (
        board_view == "PROJECTED"
        and CURRENT_PROJECTION_BOARD is not None
        and CURRENT_PROJECTION_SEASON == season_year
    )
    if showing_projection:
        status_msg = (
            f"Season {season_label}: simulated {len(CURRENT_SCHEDULED_GAMES)} remaining games "
            f"across {SIMULATION_COUNT} season runs. Current Colley ratings, opponent tiers, SOS, and venue "
            "are held fixed; conference tournament brackets and game scores are not projected."
        )
    dff = (
        CURRENT_PROJECTION_BOARD.copy()
        if showing_projection
        else CURRENT_BOARD.copy()
    )

    if showing_projection:
        if status_val == "FIELD":
            dff = dff[dff["Field_Probability"] > 0]
        elif status_val == "AUTO_BIDS":
            dff = dff[dff["Auto_Bid_Probability"] > 0]
        elif status_val == "Auto-Bid":
            dff = dff[dff["Status"] == "Auto-Bid"]
        elif status_val == "Projected Auto-Bid":
            dff = dff[
                (dff["Status"] != "Auto-Bid")
                & (dff["Auto_Bid_Probability"] > 0)
            ]
        elif status_val == "At-Large":
            dff = dff[
                (dff["Field_Probability"] > dff["Auto_Bid_Probability"])
            ]
        elif status_val in ("Likely in field", "Bubble", "Long shot"):
            dff = dff[dff["Projection_Status"] == status_val]
        elif status_val == "DQ (<= .500 Conf)":
            dff = dff[~dff["Passes_Conf_Gate"]]
    else:
        if status_val == "FIELD":
            dff = dff[dff["Status"].isin(["Auto-Bid", "Projected Auto-Bid", "At-Large"])]
        elif status_val == "AUTO_BIDS":
            dff = dff[dff["Status"].isin(["Auto-Bid", "Projected Auto-Bid"])]
        elif status_val not in ("ALL", "Likely in field", "Bubble", "Long shot"):
            dff = dff[dff["Status"] == status_val]
        elif status_val in ("Likely in field", "Bubble", "Long shot"):
            status_msg = "Select Projected board view to use projection probability filters."

    if conf_val != "ALL":
        dff = dff[dff["Conference"] == conf_val]

    actual_columns = [
        "Overall_Rank", "Projected_Seed", "Region", "Status", "Team", "Conference",
        "Record", "Conf_Record", "Selection_Score", "Raw_Points", "Dom_Bonus",
        "First_Four", "Colley_Rank", "Colley_SOS", "Passes_Conf_Gate", "Passes_Road_Gate",
    ]
    projection_columns = [
        "Projection_Rank", "Team", "Conference", "Record", "Projection_Record",
        "Projection_Win_Range", "Projection_Selection_Score", "Projection_Score_Range",
        "Field_Probability", "Auto_Bid_Probability", "Projection_Status",
    ]
    displayed_columns = projection_columns if showing_projection else actual_columns
    table_columns = [
        {"name": column.replace("_", " "), "id": column}
        for column in displayed_columns
    ]
    sort_by = [
        {
            "column_id": "Field_Probability" if showing_projection else "Overall_Rank",
            "direction": "desc" if showing_projection else "asc",
        }
    ]
    conf_options = [{"label": "All Conferences", "value": "ALL"}] + [
        {"label": c, "value": c} for c in sorted(CURRENT_BOARD["Conference"].unique())
    ]
    return (
        dff.to_dict("records"),
        table_columns,
        sort_by,
        CURRENT_CONFERENCE_SUMMARY.to_dict("records"),
        conf_options,
        status_msg,
        f"{len(CURRENT_BOARD):,}",
        f"{len(CURRENT_GAMES) // 2:,}",
        str(CURRENT_FIELD_SIZE),
    )

if __name__ == "__main__":
    app.run(debug=True)
