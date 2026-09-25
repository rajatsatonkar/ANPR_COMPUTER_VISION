import sqlite3
from datetime import datetime
from backend.config import DB_PATH

#
# ---------------------------------------------------
#  DATABASE INITIALIZATION
# ---------------------------------------------------
#

def get_connection():
    """
    Returns a SQLite connection with row factory enabled.
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Creates database tables if they do not already exist.
    Called once on FastAPI startup.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS plates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number_plate TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)

    # Vehicles table for authorization (allowed/blocked)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            plate TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'unknown'
        )
    """)

    conn.commit()
    conn.close()


#
# ---------------------------------------------------
#  CRUD OPERATIONS
# ---------------------------------------------------
#

def insert_plate(plate_number: str):
    """
    Inserts a new plate detection record.
    """
    conn = get_connection()
    cur = conn.cursor()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        INSERT INTO plates (number_plate, timestamp)
        VALUES (?, ?)
    """, (plate_number, now))

    conn.commit()
    conn.close()


def set_vehicle_status(plate: str, status: str):
    """
    Insert or update the vehicle authorization status.
    Status should be one of: 'allowed', 'blocked', 'unknown'.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("INSERT OR REPLACE INTO vehicles (plate, status) VALUES (?, ?)", (plate, status))

    conn.commit()
    conn.close()


def get_vehicle_status(plate: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT plate, status FROM vehicles WHERE plate = ?", (plate,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_vehicles():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT plate, status FROM vehicles ORDER BY plate")
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def plate_exists(plate_number: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM plates WHERE number_plate = ? LIMIT 1", (plate_number,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def delete_plate_by_number(plate_number: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM plates WHERE number_plate = ?", (plate_number,))
    conn.commit()
    conn.close()


def get_all_plates():
    """
    Returns a list of all recorded plates.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM plates ORDER BY id DESC")
    rows = cur.fetchall()

    conn.close()
    return [dict(row) for row in rows]


def clear_database():
    """
    Deletes all rows (used for debugging).
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM plates")

    conn.commit()
    conn.close()
