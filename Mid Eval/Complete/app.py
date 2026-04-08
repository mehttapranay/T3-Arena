import os
import base64
import pymongo
import mysql.connector
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
import facial_recognition_module
from dotenv import load_dotenv

# load up env vars like db passwords and uris
load_dotenv()

app = FastAPI()

# we need this to securely manage our user sessions instead of bare cookies
app.add_middleware(SessionMiddleware, secret_key="some_random_secret_string")

# throw on some cors so our frontend can actually talk to us without browser errors
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- db helpers --
def get_sql():
    # just hooks us up to the main mysql arena database
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME", "arena_db")
    )

def get_mg_imgs():
    # pulls profile pictures into memory as base64 strings so the face scanner can do its thing
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
    # big helper func to fetch and crunch player match stats for both lobby and leaderboard views
    db = get_sql()
    cur = db.cursor(dictionary=True)
    # grab win counts and total games to calculate the winrate
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
        # quick inline math to return 0 instead of blowing up throwing division errors
        win_r = round(wins / tot * 100, 1) if tot > 0 else 0.0
        
        # figure out what they are doing right now
        sts = "fighting" if p['is_fighting'] else "online" if p['is_online'] else "offline"

        data = {"uid": p['uid'], "name": p['name'], "elo_rating": p['elo_rating'], "winrate": win_r, "status": sts}
        
        # leaderboard specifically needs the rank passed down
        if incl_rnk:
            data['rank'] = i + 1
        plyrs.append(data)
    return plyrs

# -- routes --

@app.get('/')
def home():
    # basic heartbeat check to see if the api is alive
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
        # scrub out the browser b64 prefix if it hitched a ride
        cln_img = b64_img.split(',')[1] if ',' in b64_img else b64_img
        mg_db = get_mg_imgs()
        
        if not mg_db:
            return JSONResponse(status_code=500, content={"success": False, "message": "No images in database"})

        # feed the image into our blackbox face auth module
        m_uid = facial_recognition_module.find_closest_match(cln_img, mg_db)
        if not m_uid:
            print("No face match found.")
            return JSONResponse(status_code=401, content={"success": False, "message": "Face not recognised"})

        sql_db = get_sql()
        cur = sql_db.cursor(dictionary=True)
        cur.execute("SELECT uid, name, elo_rating FROM users WHERE uid = %s", (m_uid,))
        usr = cur.fetchone()

        if not usr:
            cur.close()
            sql_db.close()
            return JSONResponse(status_code=401, content={"success": False, "message": "User not found"})

        # user checked out okay, log them in on the db side
        cur.execute("UPDATE users SET is_online = TRUE WHERE uid = %s", (m_uid,))
        sql_db.commit()
        cur.close()
        sql_db.close()

        # toss the important stuff into the user session
        req.session['uid'], req.session['name'] = usr['uid'], usr['name']
        print(f"Login: {usr['name']} ({usr['uid']})")
        
        return {"success": True, "uid": usr['uid'], "name": usr['name'], "elo_rating": usr['elo_rating']}

    except Exception as e:
        print(f"Server err: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

@app.post('/logout')
async def logout(req: Request):
    try:
        inc_data = await req.json()
    except Exception:
        # maybe they closed the tab abruptly and sent nothing
        inc_data = {}
        
    fn_uid = inc_data.get('uid')
    ck_uid = req.session.get('uid')
    
    # prefer whatever the frontend sent, otherwise lean on our cookie memory
    tgt_uid = fn_uid or ck_uid
    
    print(f"\n[LOGOUT] Request for UID: '{tgt_uid}'")
    
    if tgt_uid:
        try:
            db = get_sql()
            cur = db.cursor()
            cur.execute("UPDATE users SET is_online = FALSE WHERE uid = %s", (tgt_uid,))
            db.commit()
            cur.close()
            db.close()
            print(f"[MySQL] is_online FALSE for '{tgt_uid}'")
        except Exception as e:
            print(f"[MySQL] Logout err: {e}")
            
    # only dump the session contents if the tab matches
    if tgt_uid == ck_uid:
        req.session.clear()
        print("[Session] Cleared.")
    else:
        print(f"[Session] Kept for ({ck_uid}).")

    return {"success": True}

@app.get('/api/players')
def get_plyrs():
    try:
        # simply grab all the stats and ship them off to the lobby
        return {"players": get_usr_stats()}
    except Exception as e:
        print(f"/api/players err: {e}")
        return JSONResponse(status_code=500, content={"players": [], "error": str(e)})

@app.get('/api/leaderboard')
def get_ldrbd():
    try:
        # leaderboard basically just piggybacks off the players query but slaps ranks on them
        return {"players": get_usr_stats(incl_rnk=True)}
    except Exception as e:
        print(f"/api/leaderboard err: {e}")
        return JSONResponse(status_code=500, content={"players": [], "error": str(e)})

if __name__ == '__main__':
    # spin up the dev server on port 5001 to mimic the old flask setup
    uvicorn.run("app:app", host="127.0.0.1", port=5001, reload=True)