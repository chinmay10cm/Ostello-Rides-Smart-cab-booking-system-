"""
OSTELLO RIDES — Flask Backend
CBD Belapur, Navi Mumbai
"""

from flask import Flask, render_template, request, jsonify, session, g
import sqlite3, json, requests, hashlib, os
from datetime import datetime, date
from functools import wraps

app = Flask(__name__, template_folder='../frontend/templates',
            static_folder='../frontend/static')
app.secret_key = os.environ.get('SECRET_KEY', 'ostello-rides-dev-secret-change-in-prod')

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'database', 'ostello.db')
OSRM_BASE = 'https://router.project-osrm.org/route/v1/foot'
OSTELLO_LAT, OSTELLO_LON = 19.0176, 73.0360   # 171 Parsik Hill, CBD Belapur

# ─── DB HELPERS ──────────────────────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db: db.close()

def init_db():
    schema = os.path.join(os.path.dirname(__file__), '..', 'database', 'schema.sql')
    with app.app_context():
        db = get_db()
        with open(schema) as f:
            db.executescript(f.read())
        db.commit()

def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rv = cur.fetchall()
    return (rv[0] if rv else None) if one else rv

def mutate(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur.lastrowid

# ─── AUTH HELPERS ─────────────────────────────────────────────────────────────

def pin_hash(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Not logged in', 'code': 401}), 401
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') not in ('admin',):
            return jsonify({'error': 'Admin only', 'code': 403}), 403
        return f(*args, **kwargs)
    return decorated

# ─── SCHEDULING LOGIC ─────────────────────────────────────────────────────────

def time_to_mins(t: str) -> int:
    h, m = map(int, t.split(':'))
    return h * 60 + m

def mins_to_time(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"

def cluster_and_schedule(user_time: str, ride_type: str, user_id: int):
    """
    Find nearby bookings within ±15 min, average the times,
    snap to nearest 5 min.  Returns (scheduled_time, group_id_or_None).
    """
    t_min = time_to_mins(user_time)
    today = date.today().isoformat()

    # Find open groups for same type + same day within ±15 min
    open_groups = query(
        """SELECT rg.id, rg.scheduled_time,
                  COUNT(b.id) AS pax
           FROM ride_groups rg
           JOIN bookings b ON b.group_id = rg.id
           WHERE rg.type = ? AND rg.status = 'open'
             AND DATE(rg.created_at) = ?
           GROUP BY rg.id
           HAVING pax < 10""",
        (ride_type, today)
    )

    best_group = None
    best_diff  = 9999

    for g in open_groups:
        g_min = time_to_mins(g['scheduled_time'])
        diff  = abs(g_min - t_min)
        if diff <= 15 and diff < best_diff:
            best_diff  = diff
            best_group = g

    if best_group:
        # Recalculate average time including new booking
        pax_times = query(
            "SELECT preferred_time FROM bookings WHERE group_id = ?",
            (best_group['id'],)
        )
        all_mins = [time_to_mins(r['preferred_time']) for r in pax_times] + [t_min]
        avg = round(sum(all_mins) / len(all_mins) / 5) * 5
        new_time = mins_to_time(avg)

        # Update group scheduled time
        mutate("UPDATE ride_groups SET scheduled_time = ? WHERE id = ?",
               (new_time, best_group['id']))
        return new_time, best_group['id']

    # No suitable group — create a new one
    snapped = mins_to_time(round(t_min / 5) * 5)
    gid = mutate(
        "INSERT INTO ride_groups (type, scheduled_time) VALUES (?, ?)",
        (ride_type, snapped)
    )
    return snapped, gid

def osrm_route(stops):
    """
    stops: list of {lat, lon, label}
    Returns {distance_km, duration_min, ordered_stops} or None
    """
    if len(stops) < 2:
        return None
    coords = ';'.join(f"{s['lon']},{s['lat']}" for s in stops)
    try:
        r = requests.get(
            f"{OSRM_BASE}/{coords}",
            params={'overview': 'false', 'steps': 'false'},
            timeout=6
        )
        data = r.json()
        if data.get('code') == 'Ok':
            route = data['routes'][0]
            return {
                'distance_km':  round(route['distance'] / 1000, 1),
                'duration_min': round(route['duration'] / 60),
                'ordered_stops': stops
            }
    except Exception:
        pass
    return None

# ─── AUTH ROUTES ──────────────────────────────────────────────────────────────

@app.route('/api/auth/register', methods=['POST'])
def register():
    d = request.json
    name, phone, pin = d.get('name','').strip(), d.get('phone','').strip(), d.get('pin','')
    room = d.get('room_number', '').strip()
    if not all([name, phone, len(pin) == 4]):
        return jsonify({'error': 'name, phone and 4-digit pin required'}), 400
    existing = query("SELECT id FROM users WHERE phone = ?", (phone,), one=True)
    if existing:
        return jsonify({'error': 'Phone already registered'}), 409
    uid = mutate(
        "INSERT INTO users (name, phone, room_number, pin_hash) VALUES (?, ?, ?, ?)",
        (name, phone, room, pin_hash(pin))
    )
    session['user_id'] = uid
    session['name']    = name
    session['role']    = 'resident'
    return jsonify({'message': 'Registered', 'user_id': uid})

@app.route('/api/auth/login', methods=['POST'])
def login():
    d = request.json
    phone, pin = d.get('phone','').strip(), d.get('pin','')
    user = query("SELECT * FROM users WHERE phone = ? AND pin_hash = ?",
                 (phone, pin_hash(pin)), one=True)
    if not user:
        return jsonify({'error': 'Invalid phone or PIN'}), 401
    session['user_id'] = user['id']
    session['name']    = user['name']
    session['role']    = user['role']
    return jsonify({'message': 'Logged in', 'name': user['name'], 'role': user['role']})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out'})

@app.route('/api/auth/me')
def me():
    if 'user_id' not in session:
        return jsonify({'logged_in': False})
    return jsonify({'logged_in': True, 'name': session['name'], 'role': session['role']})

# ─── BOOKING ROUTES ────────────────────────────────────────────────────────────

@app.route('/api/book', methods=['POST'])
@login_required
def book_ride():
    d = request.json
    user_id = session['user_id']
    ride_type      = d.get('type')
    lat            = d.get('lat')
    lon            = d.get('lon')
    location_label = d.get('location_label', '')
    preferred_time = d.get('preferred_time')

    if not all([ride_type in ('pickup','drop'), lat, lon, preferred_time, location_label]):
        return jsonify({'error': 'Missing fields'}), 400

    # Enforce: max 1 pickup + 1 drop per user per day
    today = date.today().isoformat()
    existing = query(
        """SELECT id FROM bookings
           WHERE user_id = ? AND type = ? AND DATE(created_at) = ?
             AND status NOT IN ('cancelled','completed')""",
        (user_id, ride_type, today), one=True
    )
    if existing:
        return jsonify({'error': f'You already have a {ride_type} booking today'}), 409

    scheduled_time, group_id = cluster_and_schedule(preferred_time, ride_type, user_id)

    bid = mutate(
        """INSERT INTO bookings
           (user_id, type, lat, lon, location_label, preferred_time, scheduled_time, group_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, ride_type, lat, lon, location_label, preferred_time, scheduled_time, group_id)
    )

    # Generate / update route for group
    _update_group_route(group_id)

    booking = query("SELECT * FROM bookings WHERE id = ?", (bid,), one=True)
    group   = query("SELECT * FROM ride_groups WHERE id = ?", (group_id,), one=True)

    return jsonify({
        'booking_id':      bid,
        'group_id':        group_id,
        'preferred_time':  preferred_time,
        'scheduled_time':  scheduled_time,
        'adjusted':        scheduled_time != preferred_time,
        'pax_in_group':    query("SELECT COUNT(*) as c FROM bookings WHERE group_id = ?",
                                 (group_id,), one=True)['c'],
        'message': 'Booking confirmed'
    })

def _update_group_route(group_id):
    """Recalculate OSRM route for a group after new booking added."""
    group    = query("SELECT * FROM ride_groups WHERE id = ?", (group_id,), one=True)
    bookings = query(
        "SELECT lat, lon, location_label, type FROM bookings WHERE group_id = ?", (group_id,)
    )
    if not bookings:
        return

    ostello = {'lat': OSTELLO_LAT, 'lon': OSTELLO_LON, 'label': 'Ostello Belapur'}
    stops   = [{'lat': b['lat'], 'lon': b['lon'], 'label': b['location_label']}
               for b in bookings]

    # Drop: Ostello → all stops. Pickup: all stops → Ostello
    if group['type'] == 'drop':
        ordered = [ostello] + stops
    else:
        ordered = stops + [ostello]

    route = osrm_route(ordered)
    mutate(
        "UPDATE ride_groups SET route_data = ?, ordered_stops = ? WHERE id = ?",
        (json.dumps(route), json.dumps(ordered), group_id)
    )

@app.route('/api/bookings/my', methods=['GET'])
@login_required
def my_bookings():
    today = date.today().isoformat()
    rows = query(
        """SELECT b.*, rg.scheduled_time AS grp_time, rg.status AS grp_status,
                  v.driver_name, v.plate
           FROM bookings b
           LEFT JOIN ride_groups rg ON b.group_id = rg.id
           LEFT JOIN vehicles    v  ON rg.vehicle_id = v.id
           WHERE b.user_id = ? AND DATE(b.created_at) = ?
           ORDER BY b.created_at DESC""",
        (session['user_id'], today)
    )
    return jsonify([dict(r) for r in rows])

@app.route('/api/bookings/<int:bid>/cancel', methods=['POST'])
@login_required
def cancel_booking(bid):
    b = query("SELECT * FROM bookings WHERE id = ? AND user_id = ?",
              (bid, session['user_id']), one=True)
    if not b:
        return jsonify({'error': 'Not found'}), 404
    mutate("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (bid,))
    return jsonify({'message': 'Cancelled'})

# ─── LOCATIONS ────────────────────────────────────────────────────────────────

@app.route('/api/locations')
def system_locations():
    rows = query("SELECT * FROM system_locations WHERE active = 1 ORDER BY label")
    return jsonify([dict(r) for r in rows])

@app.route('/api/locations/saved', methods=['GET'])
@login_required
def saved_locations():
    rows = query("SELECT * FROM saved_locations WHERE user_id = ?", (session['user_id'],))
    return jsonify([dict(r) for r in rows])

@app.route('/api/locations/saved', methods=['POST'])
@login_required
def save_location():
    d = request.json
    mutate(
        "INSERT INTO saved_locations (user_id, label, lat, lon) VALUES (?, ?, ?, ?)",
        (session['user_id'], d['label'], d['lat'], d['lon'])
    )
    return jsonify({'message': 'Saved'})

# ─── ROUTE QUERY ─────────────────────────────────────────────────────────────

@app.route('/api/route', methods=['POST'])
def get_route():
    d = request.json
    stops = d.get('stops', [])
    result = osrm_route(stops)
    if not result:
        return jsonify({'error': 'Route not available'}), 502
    return jsonify(result)

# ─── ADMIN ROUTES ─────────────────────────────────────────────────────────────

@app.route('/api/admin/groups', methods=['GET'])
@login_required
@admin_required
def admin_groups():
    today = date.today().isoformat()
    groups = query(
        """SELECT rg.*, v.driver_name, v.plate,
                  COUNT(b.id) AS pax
           FROM ride_groups rg
           LEFT JOIN vehicles v ON rg.vehicle_id = v.id
           LEFT JOIN bookings b ON b.group_id = rg.id AND b.status NOT IN ('cancelled')
           WHERE DATE(rg.created_at) = ?
           GROUP BY rg.id
           ORDER BY rg.scheduled_time""",
        (today,)
    )
    result = []
    for g in groups:
        g_dict = dict(g)
        passengers = query(
            """SELECT b.*, u.name, u.room_number
               FROM bookings b JOIN users u ON b.user_id = u.id
               WHERE b.group_id = ? AND b.status NOT IN ('cancelled')""",
            (g['id'],)
        )
        g_dict['passengers'] = [dict(p) for p in passengers]
        if g_dict.get('ordered_stops'):
            g_dict['ordered_stops'] = json.loads(g_dict['ordered_stops'])
        if g_dict.get('route_data'):
            g_dict['route_data'] = json.loads(g_dict['route_data'])
        result.append(g_dict)
    return jsonify(result)

@app.route('/api/admin/groups/<int:gid>/assign', methods=['POST'])
@login_required
@admin_required
def assign_vehicle(gid):
    d = request.json
    vid = d.get('vehicle_id')
    mutate("UPDATE ride_groups SET vehicle_id = ?, status = 'assigned' WHERE id = ?", (vid, gid))
    mutate("UPDATE bookings SET status = 'assigned' WHERE group_id = ?", (gid,))
    v = query("SELECT * FROM vehicles WHERE id = ?", (vid,), one=True)
    return jsonify({'message': f'Vehicle {v["plate"]} assigned'})

@app.route('/api/admin/groups/<int:gid>/reschedule', methods=['POST'])
@login_required
@admin_required
def reschedule_group(gid):
    new_time = request.json.get('new_time')
    mutate("UPDATE ride_groups SET scheduled_time = ? WHERE id = ?", (new_time, gid))
    mutate("UPDATE bookings SET scheduled_time = ? WHERE group_id = ?", (new_time, gid))
    return jsonify({'message': f'Rescheduled to {new_time}'})

@app.route('/api/admin/vehicles', methods=['GET'])
@login_required
@admin_required
def list_vehicles():
    rows = query("SELECT * FROM vehicles WHERE active = 1")
    return jsonify([dict(r) for r in rows])

# ─── DRIVER ROUTES ────────────────────────────────────────────────────────────

@app.route('/api/driver/my-group')
@login_required
def driver_group():
    """Driver sees their assigned group for today."""
    today  = date.today().isoformat()
    driver = query("SELECT * FROM users WHERE id = ?", (session['user_id'],), one=True)
    vehicle = query("SELECT * FROM vehicles WHERE driver_name = ?", (driver['name'],), one=True)
    if not vehicle:
        return jsonify({'error': 'No vehicle assigned'}), 404
    groups = query(
        """SELECT rg.* FROM ride_groups rg
           WHERE rg.vehicle_id = ? AND DATE(rg.created_at) = ?
           ORDER BY rg.scheduled_time""",
        (vehicle['id'], today)
    )
    result = []
    for g in groups:
        gd = dict(g)
        pax = query(
            """SELECT b.location_label, b.lat, b.lon, b.type, u.name, u.room_number, u.phone
               FROM bookings b JOIN users u ON b.user_id = u.id
               WHERE b.group_id = ? AND b.status NOT IN ('cancelled','completed')""",
            (g['id'],)
        )
        gd['passengers'] = [dict(p) for p in pax]
        if gd.get('ordered_stops'):
            gd['ordered_stops'] = json.loads(gd['ordered_stops'])
        result.append(gd)
    return jsonify(result)

# ─── PAGES ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin_page():
    return render_template('admin.html')

@app.route('/driver')
def driver_page():
    return render_template('driver.html')

# ─── INIT ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        init_db()
        print('✅ Database initialised')
    app.run(debug=True, port=5001)
