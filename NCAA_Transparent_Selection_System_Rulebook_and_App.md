# NCAA Men's Basketball Transparent Selection & Seeding System

*Complete Rulebook, 2025–26 Reconstructed Bracket Simulation, and Plotly Dash Python Application*

## Part 1: The Complete Selection & Seeding Rulebook

### Article I: Core Principles

1. Current-Season Exclusivity: Only games played between NCAA Division I opponents during the current season are counted. Preseason rankings, prior-year results, returning minutes, and margin of victory are completely excluded.

2. Retroactive Dynamic Tiering: Opponent tiers are recalculated daily from scratch based on current-season Colley Matrix ratings. A game's point value automatically upgrades or downgrades as an opponent's season record evolves, locking on Selection Sunday.

### Article II: Hard Eligibility Gates (At-Large Qualification)

All 31 conference tournament champions receive automatic entry regardless of record or rank. To be eligible for one of the 37 at-large bids (or expansion Merit Play-In spots), a team must clear two binary gates:

1. The > .500 Regular-Season Conference Gate: A team must finish strictly above .500 in regular-season conference play (e.g., 11–9 or 10–8). Any team at .500 or below is automatically disqualified from at-large consideration.

2. The Non-Conference Road/Neutral Gate: A team must play at least two true road or neutral-site games against Top-100 opponents (per Colley Matrix rank) outside of conference play.

Shutout Exemption: A team finishing with 28+ overall wins and 0–1 conference losses is exempt from the non-conference road/neutral gate if power-conference opponents declined non-conference series.

### Article III: The 5-Tier Game Point Ledger

Every Division I game (regular season and conference tournament) earns points based on the opponent's current Colley Matrix rank and game location. Non-Division I games are excluded.

| Opponent Tier (Colley Rank) | Home Win | Neutral Win | Road Win | Home Loss | Neutral Loss | Road Loss |
| --- | --- | --- | --- | --- | --- | --- |
| Tier 1 (Ranks 1–25) | +6.0 | +7.5 | +9.0 | -1.0 | -0.5 | 0.0 |
| Tier 2 (Ranks 26–60) | +4.0 | +5.0 | +6.5 | -2.0 | -1.5 | -1.0 |
| Tier 3 (Ranks 61–120) | +2.0 | +2.5 | +3.5 | -3.5 | -2.5 | -2.0 |
| Tier 4 (Ranks 121–200) | +0.5 | +1.0 | +1.5 | -5.0 | -4.0 | -3.0 |
| Tier 5 (Ranks 201+ / Buy Games) | 0.0 | +0.25 | +0.5 | -8.0 | -6.5 | -5.0 |

### Article IV: Total Selection Score Formula

A team's Total Selection Score combines its schedule-adjusted game points with its locked regular-season Conference Dominance Bonus:

Total Selection Score = ( Raw Game Points × [ 1 + (Colley SOS × 0.15) ] ) + Conference Dominance Bonus

Colley SOS: The average Colley rating of all Division I opponents played, calculated iteratively strictly from wins and losses.

Conference Dominance Bonus (Locked at Regular-Season End): 0 or 1 Conference Loss = +12.0 points | 2 Conference Losses = +8.0 points | 3 Conference Losses = +4.0 points | 4+ Conference Losses = 0.0 points. Conference tournament games count on the point ledger as neutral-site games but do not erase a regular-season dominance bonus.

### Article V: Unified Seeding, Intra-Conference Shift & Merit Play-In

1. Single Live Leaderboard: All 364 Division I teams are ranked 1 through 364 in real time by Total Selection Score.

2. Field Selection (68 Teams): The 31 automatic qualifiers enter first, followed by the top 37 eligible at-large teams on the leaderboard.

3. True Seed Lines: All 68 selected teams are ordered 1 through 68 strictly by Total Selection Score. Strong mid-major champions earn top seeds, while low-major champions naturally slot onto the 15/16 lines. The lowest four auto-bids play in the First Four.

4. One-Seed Intra-Conference Shift: Teams are placed into four regions via the S-curve. If two teams from the same conference are scheduled to meet in the Round of 64 or Round of 32, the lower-ranked team shifts up or down one seed line (swapping with an adjacent team) to prevent an early conference rematch.

5. Optional 72/76-Team Merit Play-In: If expanded, the highest-ranked eligible at-large teams bumped out of the top 68 by sub-68 auto-bids compete in single-elimination play-in games for the final Round of 64 spots, while all 31 automatic conference champions advance directly to the Round of 64.

## Part 2: 2025–26 Reconstructed Auto-Seeded Field & Regional Bracket

Reconstructed 68-team tournament field using 2025–26 records, conference finishes, and automatic qualifiers under the unified leaderboard, > .500 conference gate, and one-seed intra-conference shift rules.

### Unified 68-Team Auto-Seeded Ranking (Seeds 1–16)

| Seed Line | Team 1 (Overall) | Team 2 (Overall) | Team 3 (Overall) | Team 4 (Overall) |
| --- | --- | --- | --- | --- |
| 1-Seeds | #1 Duke (32-2) [AUTO] | #2 Arizona (32-2) [AUTO] | #3 Michigan (31-3) | #4 Florida (26-7) [AUTO] |
| 2-Seeds | #5 UConn (29-5) [AUTO] | #6 Houston (28-6) | #7 Purdue (27-8) [AUTO] | #8 Iowa State (27-7) |
| 3-Seeds | #9 Gonzaga (30-3) [AUTO] | #10 Virginia (29-5) | #11 St. John's (28-6) [AUTO] | #12 Michigan State (25-7) |
| 4-Seeds | #13 Illinois (24-8) | #14 Nebraska (26-6) | #15 Arkansas (26-8) [AUTO] | #16 Alabama (23-9) |
| 5-Seeds | #17 Kansas (23-10) | #18 Vanderbilt (26-8) | #19 Saint Mary's (27-5) | #20 Saint Louis (28-5) |
| 6-Seeds | #21 Utah State (28-6) [AUTO] | #22 Miami (FL) (25-8) | #23 Louisville (23-10) | #24 North Carolina (24-8) |
| 7-Seeds | #25 Miami (Ohio) (31-1) | #26 Wisconsin (24-10) | #27 Villanova (24-8) | #28 Clemson (24-10) |
| 8-Seeds | #29 VCU (27-7) [AUTO] | #30 High Point (30-4) [AUTO] | #31 McNeese (28-5) [AUTO] | #32 BYU (23-11) |
| 9-Seeds | #33 Tennessee (22-11) | #34 Texas Tech (22-10)* | #35 Santa Clara (26-8) | #36 Akron (29-5) [AUTO]* |
| 10-Seeds | #37 South Florida (25-8) [AUTO]* | #38 Liberty (26-8) | #39 Stephen F. Austin (28-6) | #40 Belmont (26-6)* |
| 11-Seeds | #41 Georgia (22-10) | #42 UCLA (23-11) | #43 TCU (22-11) | #44 Texas A&M (21-11) |
| 12-Seeds | #45 N. Dakota St. (27-7) [AUTO] | #46 UCF (21-11) | #47 San Diego State | #48 New Mexico |
| 13-Seeds | #49 Cal Baptist (25-8) [AUTO] | #50 Northern Iowa (23-12) [AUTO] | #51 Hawaii (24-8) [AUTO] | #52 Hofstra (24-10) [AUTO] |
| 14-Seeds | #53 Tennessee St. (23-9) [AUTO] | #54 Wright State (23-11) [AUTO] | #55 Siena (23-11) [AUTO] | #56 Troy (22-11) [AUTO] |
| 15-Seeds | #57 Furman (22-12) [AUTO] | #58 Kennesaw St. (21-13) [AUTO] | #59 Queens (NC) (21-13) [AUTO] | #60 UMBC [AUTO] |
| 16-Seeds | #61 Long Island (24-10) [AUTO] | #62 Howard (24-10) [AUTO] | #63 Idaho (21-14) [AUTO] | #64 Penn / #65 Lehigh / #66 Prairie View A&M / #67-#68 [AUTO] |

> *Indicates teams shifted one seed line in regional placement to prevent Round of 64 / Round of 32 intra-conference matchups (Akron shifted from 9 to 10; Texas Tech shifted from 9 in West to 9 in Midwest).

### Regional Brackets (With One-Seed Intra-Conference Shift Applied)

#### East Region (#1 Overall Seed: Duke)

| Seed Matchup | Higher Seed | Lower Seed |
| --- | --- | --- |
| 1 vs. 16 | #1 Duke (32-2) [AUTO] | #64 Penn (18-11) / #65 Lehigh [AUTO] (First Four) |
| 8 vs. 9 | #32 BYU (23-11) [At-Large] | #33 Tennessee (22-11) [At-Large] |
| 5 vs. 12 | #17 Kansas (23-10) [At-Large] | #48 New Mexico [At-Large] |
| 4 vs. 13 | #16 Alabama (23-9) [At-Large] | #49 California Baptist (25-8) [AUTO] |
| 6 vs. 11 | #24 North Carolina (24-8) [At-Large] | #41 Georgia (22-10) [At-Large] |
| 3 vs. 14 | #9 Gonzaga (30-3) [AUTO] | #56 Troy (22-11) [AUTO] |
| 7 vs. 10 | #25 Miami (Ohio) (31-1) [At-Large] | #40 Belmont (26-6) [At-Large] (Shifted from 9) |
| 2 vs. 15 | #8 Iowa State (27-7) [At-Large] | #57 Furman (22-12) [AUTO] |

#### West Region (#2 Overall Seed: Arizona)

| Seed Matchup | Higher Seed | Lower Seed |
| --- | --- | --- |
| 1 vs. 16 | #2 Arizona (32-2) [AUTO] | #63 Idaho (21-14) / #66 Prairie View A&M [AUTO] (First Four) |
| 8 vs. 9 | #31 McNeese (28-5) [AUTO] | #34 South Florida (25-8) [AUTO] (Shifted from 10) |
| 5 vs. 12 | #18 Vanderbilt (26-8) [At-Large] | #47 San Diego State [At-Large] |
| 4 vs. 13 | #15 Arkansas (26-8) [AUTO] | #50 Northern Iowa (23-12) [AUTO] |
| 6 vs. 11 | #23 Louisville (23-10) [At-Large] | #42 UCLA (23-11) [At-Large] |
| 3 vs. 14 | #10 Virginia (29-5) [At-Large] | #55 Siena (23-11) [AUTO] |
| 7 vs. 10 | #26 Wisconsin (24-10) [At-Large] | #39 Stephen F. Austin (28-6) [At-Large] |
| 2 vs. 15 | #7 Purdue (27-8) [AUTO] | #58 Kennesaw State (21-13) [AUTO] |

#### South Region (#3 Overall Seed: Michigan)

| Seed Matchup | Higher Seed | Lower Seed |
| --- | --- | --- |
| 1 vs. 16 | #3 Michigan (31-3) [At-Large] | #62 Howard (24-10) / #67 Auto-Bid #30 [AUTO] (First Four) |
| 8 vs. 9 | #30 High Point (30-4) [AUTO] | #35 Santa Clara (26-8) [At-Large] |
| 5 vs. 12 | #19 Saint Mary's (27-5) [At-Large] | #46 UCF (21-11) [At-Large] |
| 4 vs. 13 | #14 Nebraska (26-6) [At-Large] | #51 Hawaii (24-8) [AUTO] |
| 6 vs. 11 | #22 Miami (FL) (25-8) [At-Large] | #43 TCU (22-11) [At-Large] |
| 3 vs. 14 | #11 St. John's (28-6) [AUTO] | #54 Wright State (23-11) [AUTO] |
| 7 vs. 10 | #27 Villanova (24-8) [At-Large] | #38 Liberty (26-8) [At-Large] |
| 2 vs. 15 | #6 Houston (28-6) [At-Large] | #59 Queens (NC) (21-13) [AUTO] |

#### Midwest Region (#4 Overall Seed: Florida)

| Seed Matchup | Higher Seed | Lower Seed |
| --- | --- | --- |
| 1 vs. 16 | #4 Florida (26-7) [AUTO] | #61 Long Island (24-10) / #68 Auto-Bid #31 [AUTO] (First Four) |
| 8 vs. 9 | #29 VCU (27-7) [AUTO] | #36 Texas Tech (22-10) [At-Large] (Shifted) |
| 5 vs. 12 | #20 Saint Louis (28-5) [At-Large] | #45 North Dakota State (27-7) [AUTO] |
| 4 vs. 13 | #13 Illinois (24-8) [At-Large] | #52 Hofstra (24-10) [AUTO] |
| 6 vs. 11 | #21 Utah State (28-6) [AUTO] | #44 Texas A&M (21-11) [At-Large] |
| 3 vs. 14 | #12 Michigan State (25-7) [At-Large] | #53 Tennessee State (23-9) [AUTO] |
| 7 vs. 10 | #28 Clemson (24-10) [At-Large] | #37 Akron (29-5) [AUTO] (Shifted from 9) |
| 2 vs. 15 | #5 UConn (29-5) [AUTO] | #60 UMBC [AUTO] |

## Part 3: Current Python & Plotly Dash Application

The original Word document includes a historical Python/Dash code listing. It is omitted here to avoid duplicating an outdated snapshot. The maintained application is [ncaa_selection_app.py](./ncaa_selection_app.py); see [README.md](./README.md) for local setup and run instructions.
