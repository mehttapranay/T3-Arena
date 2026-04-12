import os
import base64
import pymongo
import mysql.connector
from fastapi import FastAPI, Request, Response 
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
import facial_recognition_module
from dotenv import load_dotenv
import uuid
from fastapi import WebSocket, WebSocketDisconnect
from engine import TicTacToeEngine
from fastapi.staticfiles import StaticFiles
import asyncio 

load_dotenv()

app = FastAPI()

app.mount("/Frontend", StaticFiles(directory="Frontend"), name="frontend")

app.add_middleware(SessionMiddleware, secret_key="some_random_secret_string")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",   
        "http://127.0.0.1:8000",   
        "http://localhost:5500",
        "http://127.0.0.1:5500"
    ], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_sql():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME", "arena_db")
    )

def get_mg_imgs():
    db_dt = {}
    try:
        cn = pymongo.MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
        col = cn[os.getenv("DB_NAME", "arena_db")]["profile_images"]
        for doc in col.find({}):
            uid, b64_img = doc.get("uid"), doc.get("image_data")
            if uid and b64_img:
                db_dt[uid] = base64.b64decode(b64_img)
        cn.close()
    except Exception as e:
        print(f"Mongo load err: {e}")
    return db_dt

def get_usr_stats(incl_rnk=False):
    db = get_sql()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT u.uid, u.name, u.elo_rating, u.is_online, u.is_fighting,
               COUNT(CASE WHEN (m.player1_uid = u.uid OR m.player2_uid = u.uid) THEN 1 END) AS tot_gms,
               COUNT(CASE WHEN m.winner_uid = u.uid THEN 1 END) AS wins
        FROM users u
        LEFT JOIN match_history m ON u.uid = m.player1_uid OR u.uid = m.player2_uid
        GROUP BY u.uid, u.name, u.elo_rating, u.is_online, u.is_fighting
        ORDER BY u.elo_rating DESC
    """)
    rows = cur.fetchall()
    cur.close()
    db.close()

    plyrs = []
    for i, p in enumerate(rows):
        tot, wins = p['tot_gms'] or 0, p['wins'] or 0
        win_r = round(wins / tot * 100, 1) if tot > 0 else 0.0
        sts = "fighting" if p['is_fighting'] else "online" if p['is_online'] else "offline"

        data = {"uid": str(p['uid']), "name": p['name'], "elo_rating": p['elo_rating'], "winrate": win_r, "status": sts}
        
        if incl_rnk:
            data['rank'] = i + 1
        plyrs.append(data)
    return plyrs

@app.get('/')
def home():
    return "Arena API running."

@app.post('/login')
async def handle_login(req: Request):
    try:
        inc_data = await req.json()
    except Exception:
        inc_data = {}
        
    b64_img = inc_data.get('image')
    if not b64_img:
        return JSONResponse(status_code=400, content={"success": False, "message": "No image provided"})

    try:
        cln_img = b64_img.split(',')[1] if ',' in b64_img else b64_img
        
        mg_db = await asyncio.to_thread(get_mg_imgs)
        
        if not mg_db:
            return JSONResponse(status_code=500, content={"success": False, "message": "No images in database"})

        m_uid = await asyncio.to_thread(facial_recognition_module.find_closest_match, cln_img, mg_db)
        
        if not m_uid:
            return JSONResponse(status_code=401, content={"success": False, "message": "Face not recognised"})

        sql_db = get_sql()
        cur = sql_db.cursor(dictionary=True)
        cur.execute("SELECT uid, name, elo_rating FROM users WHERE uid = %s", (m_uid,))
        usr = cur.fetchone()

        if not usr:
            cur.close()
            sql_db.close()
            return JSONResponse(status_code=401, content={"success": False, "message": "User not found"})

        cur.execute("UPDATE users SET is_online = TRUE WHERE uid = %s", (m_uid,))
        sql_db.commit()
        cur.close()
        sql_db.close()

        req.session['uid'], req.session['name'] = str(usr['uid']), usr['name']
        
        await lobby_mgr.broadcast({"type": "presence", "uid": str(usr['uid']), "status": "online"})
        
        return {"success": True, "uid": str(usr['uid']), "name": usr['name'], "elo_rating": usr['elo_rating']}

    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

@app.post('/logout')
async def logout(req: Request):
    try:
        inc_data = await req.json()
    except Exception:
        inc_data = {}
        
    fn_uid = inc_data.get('uid')
    ck_uid = req.session.get('uid')
    tgt_uid = fn_uid or ck_uid
    
    if tgt_uid:
        try:
            db = get_sql()
            cur = db.cursor()
            cur.execute("UPDATE users SET is_online = FALSE WHERE uid = %s", (tgt_uid,))
            db.commit()
            cur.close()
            db.close()
            await lobby_mgr.broadcast({"type": "presence", "uid": str(tgt_uid), "status": "offline"})
        except Exception as e:
            print(f"[MySQL] Logout err: {e}")
            
    if str(tgt_uid) == str(ck_uid):
        req.session.clear()

    return {"success": True}

@app.get('/api/players')
def get_plyrs(response: Response):
    response.headers["Cache-Control"] = "no-store, max-age=0"
    try:
        return {"players": get_usr_stats()}
    except Exception as e:
        return JSONResponse(status_code=500, content={"players": [], "error": str(e)})

@app.get('/api/leaderboard')
def get_ldrbd(response: Response):
    response.headers["Cache-Control"] = "no-store, max-age=0"
    try:
        return {"players": get_usr_stats(incl_rnk=True)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"players": [], "error": str(e)})

@app.get("/api/match-history/{target_uid}")
async def get_match_history(target_uid: str, request: Request):
    try:
        conn = get_sql()
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT m.*, u1.name as p1_name, u2.name as p2_name 
            FROM match_history m
            LEFT JOIN users u1 ON m.player1_uid = u1.uid
            LEFT JOIN users u2 ON m.player2_uid = u2.uid
            WHERE m.player1_uid = %s OR m.player2_uid = %s
            ORDER BY m.played_at DESC
        """
        cursor.execute(query, (target_uid, target_uid))
        history_list = cursor.fetchall()
        
        for match in history_list:
            if 'played_at' in match and match['played_at']:
                match['played_at'] = match['played_at'].isoformat()
        
        cursor.close()
        conn.close()
        
        return {"matches": history_list, "current_user_id": target_uid}
        
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})
    

class LobbyManager:
    def __init__(self):
        self.connections: dict[str, WebSocket] = {}

    async def connect(self, uid: str, ws: WebSocket):
        await ws.accept()
        self.connections[uid] = ws

    def disconnect(self, uid: str):
        self.connections.pop(uid, None)

    async def handle_disconnect(self, uid: str):
        self.connections.pop(uid, None)
        await asyncio.sleep(2.0)
        
        if uid not in self.connections:
            try:
                db  = get_sql()
                cur = db.cursor()
                cur.execute("UPDATE users SET is_online = FALSE WHERE uid = %s", (uid,))
                db.commit()
                cur.close()
                db.close()
            except Exception:
                pass
            await self.broadcast({"type": "presence", "uid": uid, "status": "offline"})

    async def broadcast(self, message: dict):
        dead = []
        for uid, ws in self.connections.items():
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(uid)
        for uid in dead:
            self.connections.pop(uid, None)

    async def send_to(self, uid: str, message: dict):
        ws = self.connections.get(uid)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                self.connections.pop(uid, None)

class GameRoomManager:
    def __init__(self):
        self.rooms: dict[str, dict] = {}

    def create_room(self, uid_x: str, uid_o: str, r_x: int, r_o: int) -> str:
        room_id = str(uuid.uuid4())
        self.rooms[room_id] = {
            "engine":      TicTacToeEngine(uid_x, uid_o),
            "connections": {},
            "ratings":     {uid_x: r_x, uid_o: r_o},
            "players":     [uid_x, uid_o]
        }
        return room_id

    async def connect(self, room_id: str, uid: str, ws: WebSocket) -> bool:
        await ws.accept()
        if room_id not in self.rooms:
            return False
        self.rooms[room_id]["connections"][uid] = ws
        return True

    def disconnect(self, room_id: str, uid: str):
        if room_id in self.rooms:
            self.rooms[room_id]["connections"].pop(uid, None)

    async def broadcast_room(self, room_id: str, message: dict):
        if room_id not in self.rooms:
            return
        dead = []
        for uid, ws in self.rooms[room_id]["connections"].items():
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(uid)
        for uid in dead:
            self.rooms[room_id]["connections"].pop(uid, None)

    def close_room(self, room_id: str):
        self.rooms.pop(room_id, None)

lobby_mgr = LobbyManager()
game_mgr  = GameRoomManager()
pending_challenges: dict[str, str] = {}

def get_elo(uid: str) -> int:
    try:
        db  = get_sql()
        cur = db.cursor(dictionary=True)
        cur.execute("SELECT elo_rating FROM users WHERE uid = %s", (uid,))
        row = cur.fetchone()
        cur.close(); db.close()
        return row["elo_rating"] if row else 1200
    except Exception:
        return 1200

def save_match(uid_x: str, uid_o: str, r_x: int, r_o: int,
               r_x_new: int, r_o_new: int,
               winner_uid: str | None, forfeit: bool):
    try:
        db  = get_sql()
        cur = db.cursor()
        cur.execute("UPDATE users SET elo_rating = %s WHERE uid = %s", (r_x_new, uid_x))
        cur.execute("UPDATE users SET elo_rating = %s WHERE uid = %s", (r_o_new, uid_o))
        cur.execute("UPDATE users SET is_fighting = FALSE, is_online = TRUE WHERE uid IN (%s, %s)", (uid_x, uid_o))
        cur.execute("""
            INSERT INTO match_history
                (player1_uid, player2_uid, winner_uid,
                 player1_elo_before, player2_elo_before,
                 player1_elo_after,  player2_elo_after,
                 forfeit)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (uid_x, uid_o, winner_uid, r_x, r_o, r_x_new, r_o_new, forfeit))
        db.commit()
        cur.close(); db.close()
    except Exception:
        pass

async def finalize_match(room_id: str, forfeit_winner_uid: str | None = None):
    if room_id not in game_mgr.rooms:
        return

    room    = game_mgr.rooms[room_id]
    engine  = room["engine"]
    ratings = room["ratings"]
    uid_x   = engine.players["X"]
    uid_o   = engine.players["O"]
    r_x     = ratings[uid_x]
    r_o     = ratings[uid_o]

    is_forfeit = forfeit_winner_uid is not None
    if is_forfeit:
        engine.winner = "X" if uid_x == forfeit_winner_uid else "O"

    r_x_new, r_o_new = engine.get_match_results(r_x, r_o)

    winner_uid = None
    if engine.winner and engine.winner != "DRAW":
        winner_uid = engine.players[engine.winner]

    save_match(uid_x, uid_o, r_x, r_o, r_x_new, r_o_new, winner_uid, is_forfeit)

    await game_mgr.broadcast_room(room_id, {
        "type":        "game_over",
        "winner":      engine.winner,        
        "winner_uid":  winner_uid,
        "new_ratings": {uid_x: r_x_new, uid_o: r_o_new},
        "forfeit":     is_forfeit
    })

    game_mgr.close_room(room_id)

@app.websocket("/ws/lobby/{uid}")
async def ws_lobby(ws: WebSocket, uid: str):
    await lobby_mgr.connect(uid, ws)
    try:
        db  = get_sql()
        cur = db.cursor()
        cur.execute("UPDATE users SET is_online = TRUE WHERE uid = %s", (uid,))
        db.commit(); cur.close(); db.close()
    except Exception:
        pass

    await lobby_mgr.broadcast({"type": "presence", "uid": uid, "status": "online"})

    try:
        while True:
            raw      = await ws.receive_json()
            msg_type = raw.get("type")

            if msg_type == "challenge":
                target = str(raw.get("target_uid"))
                if not target or target == uid:
                    continue
                pending_challenges[uid] = target
                await lobby_mgr.send_to(target, {
                    "type":     "challenge_received",
                    "from_uid": uid
                })

            elif msg_type == "cancel_challenge":
                target = str(raw.get("target_uid"))
                if pending_challenges.get(uid) == target:
                    pending_challenges.pop(uid, None)
                    await lobby_mgr.send_to(target, {
                        "type":     "challenge_cancelled",
                        "from_uid": uid
                    })

            elif msg_type == "challenge_response":
                challenger = str(raw.get("from_uid"))
                accepted   = raw.get("accepted", False)

                if not accepted:
                    pending_challenges.pop(challenger, None)
                    await lobby_mgr.send_to(challenger, {
                        "type":   "challenge_declined",
                        "by_uid": uid
                    })
                    continue

                if pending_challenges.get(challenger) != uid:
                    continue

                pending_challenges.pop(challenger, None)

                r_challenger = get_elo(challenger)
                r_acceptor   = get_elo(uid)

                room_id = game_mgr.create_room(challenger, uid, r_challenger, r_acceptor)

                try:
                    db  = get_sql()
                    cur = db.cursor()
                    cur.execute(
                        "UPDATE users SET is_fighting = TRUE WHERE uid IN (%s, %s)",
                        (challenger, uid)
                    )
                    db.commit(); cur.close(); db.close()
                except Exception:
                    pass

                await lobby_mgr.send_to(challenger, {
                    "type":         "match_start",
                    "room_id":      room_id,
                    "symbol":       "X",
                    "opponent_uid": uid
                })
                await lobby_mgr.send_to(uid, {
                    "type":         "match_start",
                    "room_id":      room_id,
                    "symbol":       "O",
                    "opponent_uid": challenger
                })

    except WebSocketDisconnect:
        asyncio.create_task(lobby_mgr.handle_disconnect(uid))

@app.websocket("/ws/game/{room_id}/{uid}")
async def ws_game(ws: WebSocket, room_id: str, uid: str):
    ok = await game_mgr.connect(room_id, uid, ws)
    if not ok:
        await ws.close(code=4004)
        return

    room   = game_mgr.rooms[room_id]
    engine = room["engine"]

    await ws.send_json({
        "type":         "board_state",
        "board":        engine.board,
        "current_turn": engine.current_turn,
        "players":      engine.players
    })

    try:
        while True:
            raw = await ws.receive_json()

            if raw.get("type") == "move":
                row = raw.get("row")
                col = raw.get("col")

                success, msg = engine.make_move(uid, row, col)

                if not success:
                    await ws.send_json({"type": "move_rejected", "reason": msg})
                    continue

                await game_mgr.broadcast_room(room_id, {
                    "type":         "board_update",
                    "board":        engine.board,
                    "current_turn": engine.current_turn,
                    "last_move":    {"uid": uid, "row": row, "col": col}
                })

                if engine.winner:
                    await finalize_match(room_id)

    except WebSocketDisconnect:
        game_mgr.disconnect(room_id, uid)

        if room_id in game_mgr.rooms and not game_mgr.rooms[room_id]["engine"].winner:
            remaining = [p for p in game_mgr.rooms[room_id]["players"] if p != uid]
            if remaining:
                await finalize_match(room_id, forfeit_winner_uid=remaining[0])

if __name__ == '__main__':
    uvicorn.run("app:app", host="127.0.0.1", port=5001, reload=True)