import csv
import requests
import os
import mysql.connector
import pymongo
import base64
from dotenv import load_dotenv

cur_dir = os.path.dirname(os.path.abspath(__file__))
env_pth = os.path.join(cur_dir, ".env")
load_dotenv(env_pth)

REQ_TOUT = 5

def start_harvest(csv_path_1, csv_path_2):

    # init mysql pipe
    try:
        db_conn = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME", "arena_db")
        )
        sql_cur = db_conn.cursor()
        print("mysql pipeline secured")
    except mysql.connector.Error as err:
        print(f"mysql connection failed: {err}")
        return

    # init mongo pipe for blob storage
    try:
        mg_conn = pymongo.MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
        mg_db   = mg_conn[os.getenv("DB_NAME", "arena_db")]
        mg_col  = mg_db["profile_images"]
        print("mongodb pipeline secured")
    except Exception as e:
        print(f"mongodb connection failed: {e}")
        return

    # helper dictating fetch logic for a given target file layout
    def scrape_file(f_path, is_ta_list=False):
        print(f"\n--- scraping {os.path.basename(f_path)} ---")
        with open(f_path, mode='r', encoding='utf-8') as f:
            csv_hdr = csv.DictReader(f)

            for rw in csv_hdr:
                uid    = rw.get('uid')
                nm     = rw.get('name')
                
                # adapt parsing dynamically based on file struct difference
                if is_ta_list:
                    base_url = rw.get('url')
                    img_src = f"https://{base_url}"
                else:
                    base_url = rw.get('website_url')
                    img_src = f"https://{base_url}/images/pfp.jpg"

                print(f"fetching meta for: {nm} ({uid})")
                
                try:
                    res = requests.get(img_src, timeout=REQ_TOUT)

                    if res.status_code == 200:
                        
                        # dump core metrics to relational db
                        try:
                            sql_cur.execute("""
                                INSERT INTO users (uid, name, elo_rating, is_online)
                                VALUES (%s, %s, %s, %s)
                                ON DUPLICATE KEY UPDATE name = VALUES(name)
                            """, (uid, nm, 1200, False))
                            db_conn.commit()
                        except mysql.connector.Error as err:
                            print(f"sql fail -> {err}")

                        # dump raw bytes securely mapping to mongo collection
                        try:
                            enc_img = base64.b64encode(res.content).decode('utf-8')
                            mg_col.update_one(
                                {"uid": uid},
                                {"$set": {"uid": uid, "image_data": enc_img}},
                                upsert=True
                            )
                        except Exception as e:
                            print(f"mongo fail -> {e}")

                    elif res.status_code == 404:
                        # soft fail, setup minimal records over sql
                        try:
                            sql_cur.execute("""
                                INSERT INTO users (uid, name, elo_rating, is_online)
                                VALUES (%s, %s, %s, %s)
                                ON DUPLICATE KEY UPDATE name = VALUES(name)
                            """, (uid, nm, 1200, False))
                            db_conn.commit()
                            print(f"no pfp resolving for {nm}, writing stubbed baseline")
                        except mysql.connector.Error as err:
                            print(f"sql stub fail -> {err}")
                    else:
                        pass # unhandled http rejects skipped directly
                        
                except Exception:
                    print(f"timeout scraping record {uid}")

    # cycle thru datasets
    scrape_file(csv_path_1, is_ta_list=False)
    scrape_file(csv_path_2, is_ta_list=True)

    # teardown routines
    if db_conn.is_connected():
        sql_cur.close()
        db_conn.close()
        print("\nmysql tore down correctly")

    mg_conn.close()
    print("mongodb tore down correctly")
    print("harvest routine finalized")

if __name__ == "__main__":
    csv_1 = os.path.join(cur_dir, 'batch_data.csv')
    csv_2 = os.path.join(cur_dir, 'ta_data.csv')
    start_harvest(csv_1, csv_2)