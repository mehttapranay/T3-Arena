import mysql.connector
def calculate_elo(player_elo,opponent_elo,matchoutcome):
    # Calculate expected win probability (E)
    expected_prob = 1 / (1 + 10 ** ((opponent_elo - player_elo) / 400))
    
    # Calculate the new rating
    new_rating = player_elo + 32 * (matchoutcome - expected_prob)
        # Return as a rounded integer
    return int(round(new_rating))

# process match results and update database
def process_match_result(db, winner_uid, loser_uid, is_draw=False):
    cur = db.cursor(dictionary=True)

    try:
        # grab current elos first
        cur.execute(
            "SELECT uid, elo_rating FROM users WHERE uid IN (%s, %s)", 
            (winner_uid, loser_uid)
        )
        players = {row['uid']: row['elo_rating'] for row in cur.fetchall()}
        
        # bail if a player is missing
        if winner_uid not in players or loser_uid not in players:
            print("db error: player not found")
            return False

        win_elo = players[winner_uid]
        lose_elo = players[loser_uid]

        # calculate new scores
        if is_draw:
            new_win_elo = calculate_elo(win_elo, lose_elo, 0.5)
            new_lose_elo = calculate_elo(lose_elo, win_elo, 0.5)
            actual_winner = None 
        else:
            new_win_elo = calculate_elo(win_elo, lose_elo, 1.0)
            new_lose_elo = calculate_elo(lose_elo, win_elo, 0.0)
            actual_winner = winner_uid

        # save new ratings and unlock players
        cur.execute(
            "UPDATE users SET elo_rating = %s, is_fighting = FALSE WHERE uid = %s", 
            (new_win_elo, winner_uid)
        )
        
        cur.execute(
            "UPDATE users SET elo_rating = %s, is_fighting = FALSE WHERE uid = %s", 
            (new_lose_elo, loser_uid)
        )

        # log the match history
        cur.execute(
            "INSERT INTO match_history (player1_uid, player2_uid, winner_uid) VALUES (%s, %s, %s)", 
            (winner_uid, loser_uid, actual_winner)
        )

        db.commit()
        return True

    except Exception as e:
        # cancel transaction on error
        db.rollback()
        print(f"match update failed: {e}")
        return False

    finally:
        cur.close()