# _*_ coding: utf-8 _*_
# @Time : 2026/1/23 14:22 
# @Author : lxf 
# @Version：V 0.1
# @File : data_analysis.py
# @desc : Data analysis and statistics operations

import sqlite3
import logging
import json
from datetime import date, datetime
from collections import defaultdict
from .base import get_db_connection


def update_daily_stats(player_id: int, hands_played: int = 0, net_chips: int = 0):
    """
    更新当日数据统计，player_daily_stats表
    
    :param player_id: The player's ID
    :param hands_played: Number of hands to add
    :param net_chips: Net chips to add
    """
    conn = get_db_connection()
    if not conn:
        return

    today = date.today().isoformat()

    try:
        conn.execute("""
                     INSERT INTO player_daily_stats (stat_date, player_id, hands_played, net_chips)
                     VALUES (?, ?, ?, ?)
                     ON CONFLICT(stat_date, player_id) DO UPDATE SET hands_played = hands_played + excluded.hands_played,
                                                                     net_chips    = net_chips + excluded.net_chips
                     """, (today, player_id, hands_played, net_chips))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Error updating daily stats for player {player_id}: {e}")
    finally:
        conn.close()


def update_lifetime_stats(player_id: int, hands_played: int = 0, net_chips: int = 0,
                          vpip: int = 0, pfr: int = 0, threebet: int = 0,
                          agg_bets: int = 0, agg_calls: int = 0, wtsd: int = 0, wsd: int = 0,
                          net_bb: float = 0.0):
    """
    Update player's lifetime stats.
    Uses upsert logic.
    """
    conn = get_db_connection()
    if not conn:
        return

    try:
        # Check if record exists, if not create it
        cursor = conn.execute("SELECT player_id FROM player_lifetime_stats WHERE player_id = ?", (player_id,))
        if not cursor.fetchone():
            conn.execute("INSERT INTO player_lifetime_stats (player_id) VALUES (?)", (player_id,))

        # Update stats
        conn.execute("""
                     UPDATE player_lifetime_stats
                     SET hands_played    = hands_played + ?,
                         net_chips       = net_chips + ?,
                         vpip_hands      = vpip_hands + ?,
                         pfr_hands       = pfr_hands + ?,
                         threebet_hands  = threebet_hands + ?,
                         agg_bets_raises = agg_bets_raises + ?,
                         agg_calls       = agg_calls + ?,
                         wtsd_hands      = wtsd_hands + ?,
                         wsd_hands       = wsd_hands + ?,
                         net_bb          = net_bb + ?,
                         updated_at      = datetime('now')
                     WHERE player_id = ?
                     """, (hands_played, net_chips, vpip, pfr, threebet, agg_bets, agg_calls, wtsd, wsd, net_bb, player_id))

        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Error updating lifetime stats for player {player_id}: {e}")
    finally:
        conn.close()


def get_daily_ranking_list():
    """
    Get daily ranking list.
    Returns: List of (rank, nickname, chips, net_chips)
    """
    conn = get_db_connection()
    if not conn:
        return []

    try:
        today = date.today().isoformat()
        cursor = conn.execute("""
                              SELECT COALESCE(p.nickname, p.username) as name, w.chips, s.net_chips
                              FROM player_daily_stats s
                                       JOIN players p ON s.player_id = p.id
                                       JOIN wallet w ON s.player_id = w.player_id
                              WHERE s.stat_date = ?
                              ORDER BY s.net_chips DESC
                              """, (today,))
        rows = cursor.fetchall()

        ranking = []
        for i, row in enumerate(rows, 1):
            ranking.append((i, row['name'], row['chips'], row['net_chips']))

        return ranking
    except sqlite3.Error as e:
        logging.error(f"Error getting daily ranking: {e}")
        return []
    finally:
        conn.close()


def get_player_analysis_data(player_id: int):
    """
    Fetch all analysis data for a player to populate the dashboard.
    """
    conn = get_db_connection()
    if not conn:
        return None

    data = {
        "summary": {},
        "profit_chart": {},
        "radar_chart": {},
        "tech_stats": {},
        "position_stats": {},
        "hand_matrix": {},
        "top_hands": []
    }

    try:
        # 1. Lifetime Stats (Summary & Tech Stats)
        cursor = conn.execute("""
                              SELECT *
                              FROM player_lifetime_stats
                              WHERE player_id = ?
                              """, (player_id,))
        stats = cursor.fetchone()

        if stats:
            # Summary
            data["summary"]["total_hands"] = stats["hands_played"]
            data["summary"]["total_profit"] = stats["net_chips"]

            # BB/100 calculation
            # Assuming we can calculate it or it's stored. Stored is better.
            data["summary"]["bb_100"] = round(stats["net_bb"] / (stats["hands_played"] / 100), 2) if stats[
                                                                                                         "hands_played"] > 0 else 0

            # Tech Stats
            vpip = round((stats["vpip_hands"] / stats["hands_played"] * 100), 1) if stats["hands_played"] > 0 else 0
            pfr = round((stats["pfr_hands"] / stats["hands_played"] * 100), 1) if stats["hands_played"] > 0 else 0

            # AF = (Bets + Raises) / Calls
            af = round(stats["agg_bets_raises"] / stats["agg_calls"], 1) if stats["agg_calls"] > 0 else 0

            data["tech_stats"]["vpip"] = vpip
            data["tech_stats"]["pfr"] = pfr
            data["tech_stats"]["af"] = af

            # For Radar Chart
            # VPIP, PFR, Aggression(AF), 3-Bet(Need col), WTSD, C-Bet(Need col)
            # Using placeholders for missing cols or deriving them
            wtsd = round((stats["wtsd_hands"] / stats["hands_played"] * 100), 1) if stats["hands_played"] > 0 else 0

            # 3-Bet freq (approximate if not strictly tracked as % opportunity)
            # stored "threebet_hands" is count. We'll just use raw count / hands for now or 0 if not tracked properly yet
            three_bet = round((stats["threebet_hands"] / stats["hands_played"] * 100), 1) if stats[
                                                                                                 "hands_played"] > 0 else 0

            data["radar_chart"] = {
                "values": [vpip, pfr, af * 10, three_bet, wtsd, 50],  # Scaling AF by 10 for radar, C-Bet placeholder 50
                "labels": ['VPIP', 'PFR', 'AF x10', '3-Bet', 'WTSD', 'C-Bet']
            }
        else:
            # Defaults if no stats
            data["summary"] = {"total_hands": 0, "total_profit": 0, "bb_100": 0}
            data["tech_stats"] = {"vpip": 0, "pfr": 0, "af": 0}
            data["radar_chart"] = {"values": [0, 0, 0, 0, 0, 0], "labels": []}

        # 2. Best Pot
        cursor = conn.execute("""
                              SELECT h.total_pot, h.board_cards, hp.is_winner, hp.net_chips, hp.hole_cards
                              FROM hand_players hp
                                       JOIN hands h ON hp.hand_id = h.id
                              WHERE hp.player_id = ?
                                AND hp.net_chips > 0
                              ORDER BY hp.net_chips DESC
                              LIMIT 1
                              """, (player_id,))
        best_hand = cursor.fetchone()
        if best_hand:
            data["summary"]["best_pot"] = best_hand[
                "net_chips"]  # Showing Net Win as "Best Pot" contribution or Total Pot?
            # UI says "Best Pot" but "Win with AA". Usually means the pot size.
            # But the value displayed is 2800. Let's use net_chips for "Profit" or total_pot for "Pot Size".
            # The label is "Best Pot", usually means the biggest pot won.
            data["summary"]["best_pot_val"] = best_hand["total_pot"]
            data["summary"]["best_pot_desc"] = f"Win with {best_hand['hole_cards'] or '??'}"
        else:
            data["summary"]["best_pot_val"] = 0
            data["summary"]["best_pot_desc"] = "N/A"

        # 3. Profit Chart (Last 30 entries)
        cursor = conn.execute("""
                              SELECT stat_date, net_chips, hands_played
                              FROM player_daily_stats
                              WHERE player_id = ?
                              ORDER BY stat_date ASC
                              LIMIT 30
                              """, (player_id,))
        daily_rows = cursor.fetchall()

        # Accumulate profit for the line chart
        labels = []
        profit_data = []
        running_profit = 0

        # We need to start from lifetime profit - sum(displayed days)? No, usually just cumulative over the period or lifetime.
        # Let's just show cumulative for the period for simplicity.

        for row in daily_rows:
            labels.append(row["stat_date"])
            running_profit += row["net_chips"]
            profit_data.append(running_profit)

        data["profit_chart"] = {
            "labels": labels,
            "data": profit_data
        }

        # 4. Position Stats
        # 'BTN', 'SB', 'BB', 'UTG', 'UTG+1', 'UTG+2', 'UTG+3', 'MP', 'HJ', 'CO'
        # Map them to standard 6-max or 9-max buckets for the chart
        cursor = conn.execute("""
                              SELECT position_name, SUM(net_chips) as profit
                              FROM hand_players
                              WHERE player_id = ?
                              GROUP BY position_name
                              """, (player_id,))
        pos_rows = cursor.fetchall()

        pos_map = defaultdict(int)
        for row in pos_rows:
            pos = row["position_name"]
            # Normalize positions if necessary
            if pos:
                pos_map[pos] += row["profit"]

        # Ensure order for chart: SB, BB, UTG, MP, CO, BTN
        ordered_pos = ['SB', 'BB', 'UTG', 'MP', 'CO', 'BTN']
        pos_values = []
        for p in ordered_pos:
            # Simple mapping for full ring to 6-max labels if needed, or just exact match
            # For now, exact match. If UTG+1 exists, it's ignored or needs mapping.
            val = pos_map.get(p, 0)
            # Aggregate UTG+ into UTG, MP/HJ into MP for simplified chart
            if p == 'UTG':
                val += pos_map.get('UTG+1', 0) + pos_map.get('UTG+2', 0)
            if p == 'MP':
                val += pos_map.get('HJ', 0)

            pos_values.append(val)

        data["position_stats"] = {
            "labels": ordered_pos,
            "values": pos_values
        }

        # 5. Hand Matrix (Last 1000 hands)
        cursor = conn.execute("""
                              SELECT hole_cards, net_chips
                              FROM hand_players
                              WHERE player_id = ?
                                AND hole_cards IS NOT NULL
                              ORDER BY hand_id DESC
                              LIMIT 1000
                              """, (player_id,))
        hand_rows = cursor.fetchall()

        # Processing to grid: AA, AKs...
        # We need a dictionary: {'AA': 150, 'AKs': -20, ...} (aggregated profit)
        matrix_data = defaultdict(int)

        def normalize_hand(cards_str):
            # cards_str expected like "AhKd" or "['Ah', 'Kd']" or "[[14, 0], [13, 1]]"
            # Parse it
            try:
                if cards_str.startswith('['):
                    import ast
                    cards = ast.literal_eval(cards_str)
                else:
                    # simplistic parse if just concatenated "AhKd"
                    cards = [cards_str[0:2], cards_str[2:4]]
            except:
                return None

            if len(cards) != 2: return None

            # Map for int ranks
            int_to_rank = {
                14: 'A', 13: 'K', 12: 'Q', 11: 'J', 10: 'T',
                9: '9', 8: '8', 7: '7', 6: '6', 5: '5', 4: '4', 3: '3', 2: '2'
            }

            # Sort by rank to ensure AK (A high) not KA
            ranks_order = "23456789TJQKA"
            r1, s1 = cards[0][0], cards[0][1]
            r2, s2 = cards[1][0], cards[1][1]

            # Normalize r1, r2 to string chars if they are ints
            if isinstance(r1, int): r1 = int_to_rank.get(r1, str(r1))
            if isinstance(r2, int): r2 = int_to_rank.get(r2, str(r2))

            idx1 = ranks_order.index(r1) if r1 in ranks_order else -1
            idx2 = ranks_order.index(r2) if r2 in ranks_order else -1

            if idx1 < idx2:
                r1, r2 = r2, r1
                s1, s2 = s2, s1

            suffix = 's' if s1 == s2 else 'o'
            if r1 == r2:
                return r1 + r2  # AA
            else:
                return r1 + r2 + suffix  # AKs or AKo

        for row in hand_rows:
            h_str = row["hole_cards"]
            if not h_str: continue

            key = normalize_hand(h_str)
            if key:
                matrix_data[key] += row["net_chips"]

        data["hand_matrix"] = dict(matrix_data)

        # 6. Top Recent Hands
        cursor = conn.execute("""
                              SELECT h.id,
                                     h.total_pot,
                                     h.board_cards,
                                     hp.hole_cards,
                                     hp.position_name,
                                     hp.net_chips,
                                     hp.is_winner
                              FROM hand_players hp
                                       JOIN hands h ON hp.hand_id = h.id
                              WHERE hp.player_id = ?
                              ORDER BY ABS(hp.net_chips) DESC -- Biggest wins OR losses
                              LIMIT 5
                              """, (player_id,))
        top_hands_rows = cursor.fetchall()
        top_hands = []
        
        for row in top_hands_rows:
            hand_id = row["id"]
            
            # Fetch actions for this hand
            ac_cursor = conn.execute("""
                SELECT ha.street, ha.action_type, ha.amount, ha.player_id, 
                       COALESCE(p.nickname, p.username) as name
                FROM hand_actions ha
                LEFT JOIN players p ON ha.player_id = p.id
                WHERE ha.hand_id = ?
                ORDER BY ha.action_num ASC
            """, (hand_id,))
            
            actions = []
            for ac in ac_cursor.fetchall():
                actions.append({
                    "street": ac["street"],
                    "action": ac["action_type"],
                    "amount": ac["amount"],
                    "player_id": ac["player_id"],
                    "name": ac["name"]
                })

            top_hands.append({
                "hand_id": hand_id,
                "hole_cards": row["hole_cards"],
                "board_cards": row["board_cards"],
                "position": row["position_name"],
                "result": "Win" if row["net_chips"] > 0 else "Lose",
                "profit": row["net_chips"],
                "pot": row["total_pot"],
                "actions": actions
            })
            
        data["top_hands"] = top_hands

        return data

    except sqlite3.Error as e:
        logging.error(f"Error fetching player analysis data: {e}")
        return None
    finally:
        conn.close()
