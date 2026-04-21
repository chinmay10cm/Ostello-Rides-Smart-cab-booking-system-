# 🚖 Ostello Rides — Smart Cab Booking System
> CBD Belapur, Navi Mumbai | Built for Ostello Hostel residents

## What This Is
A WhatsApp-style chat UI for structured, smart shared cab booking — replacing chaotic group chats with a guided, automated system. Built on your existing OSRM open-source routing foundation.

---

## 📁 Project Structure

```
ostello-rides/
├── backend/
│   └── app.py              ← Flask app (all API routes)
├── frontend/
│   └── templates/
│       ├── index.html      ← Resident chat UI (main app)
│       ├── admin.html      ← Admin dashboard
│       └── driver.html     ← Driver route view
├── database/
│   ├── schema.sql          ← All table definitions + seed data
│   └── ostello.db          ← Auto-created on first run
├── requirements.txt
└── README.md
```

---

## ⚡ Setup in 5 Minutes

### 1. Clone & install
```bash
git clone <your-repo>
cd ostello-rides
pip install -r requirements.txt
```

### 2. Initialize the database
```bash
cd backend
python -c "from app import init_db; init_db()"
# ✅ Database initialised with locations, vehicles, default admin
```

### 3. Run the server
```bash
python app.py
# Running on http://localhost:5001
```

### 4. Open the app
- **Resident app:**   http://localhost:5001/
- **Admin panel:**    http://localhost:5001/admin
- **Driver view:**    http://localhost:5001/driver

---

## 🗄️ Database Tables

| Table | Purpose |
|---|---|
| `users` | Residents, drivers, admins (phone + PIN auth) |
| `bookings` | Each ride booking with lat/lon, time, status |
| `ride_groups` | Clustered groups of bookings sharing a vehicle |
| `vehicles` | Driver names, plates, capacities |
| `system_locations` | Admin-defined Navi Mumbai landmarks |
| `saved_locations` | Per-user favourite spots |

### Key locations pre-loaded (Navi Mumbai):
- Ostello Parsik Hill, Belapur ← home base
- CBD Belapur Station, Vashi, Kharghar, Panvel, Nerul, Seawoods
- DY Patil College, NMIMS, Inorbit Mall, Mindspace Airoli
- Palm Beach Road, Navi Mumbai Airport (future)

---

## 🧠 How Smart Scheduling Works

```
User books 9:45 drop to Vashi Station
System finds existing group at 9:30 (3 pax) for same type
Difference = 15 min → within threshold
Average: (9*60+30 + 9*60+30 + 9*60+30 + 9*60+45) / 4 = 9:33
Snap to nearest 5 min → 9:35
All bookings in group updated to 9:35
Route recalculated via OSRM with all stops
```

**Rules enforced:**
- Max 1 pickup + 1 drop per user per day
- Max 10 passengers per group/vehicle
- Auto-overflow: if group full, new group created
- No bookings for past time slots

---

## 🗺️ OSRM Routing

Uses the free public OSRM server (same as your campus navigation project):
```
https://router.project-osrm.org/route/v1/foot/{coords}
```

For drop runs: `Ostello → Stop1 → Stop2 → ... → Final`
For pickup runs: `Stop1 → Stop2 → ... → Ostello`

Returns distance (km) and duration (min) shown in the chat.

---

## 🔐 Auth System

- Phone number + 4-digit PIN
- PIN stored as SHA-256 hash (upgrade to bcrypt for production)
- Session-based (Flask sessions)
- Roles: `resident` | `driver` | `admin`

### Default login to test:
Register as a new resident on the app. For admin/driver, insert directly:
```sql
INSERT INTO users (name, phone, room_number, role, pin_hash)
VALUES ('Admin', '9999999999', NULL, 'admin', '<sha256 of your pin>');
```

---

## 🚀 API Reference

### Auth
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/auth/register` | `{name, phone, pin, room_number}` | `{user_id}` |
| POST | `/api/auth/login` | `{phone, pin}` | `{name, role}` |
| GET  | `/api/auth/me` | — | `{logged_in, name, role}` |

### Bookings
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/book` | `{type, lat, lon, location_label, preferred_time}` | `{booking_id, scheduled_time, adjusted, pax_in_group}` |
| GET  | `/api/bookings/my` | — | `[bookings with group + driver info]` |
| POST | `/api/bookings/{id}/cancel` | — | `{message}` |

### Locations
| Method | Path | Returns |
|---|---|---|
| GET | `/api/locations` | All Navi Mumbai system locations |
| GET | `/api/locations/saved` | User's saved locations |
| POST | `/api/locations/saved` | Save a new location |

### Admin (admin role required)
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/admin/groups` | — | All groups today with passengers + route |
| POST | `/api/admin/groups/{id}/assign` | `{vehicle_id}` | Assign vehicle |
| POST | `/api/admin/groups/{id}/reschedule` | `{new_time}` | Override time |
| GET | `/api/admin/vehicles` | — | All vehicles |

### Route
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/route` | `{stops: [{lat,lon,label}]}` | `{distance_km, duration_min}` |

---

## 🔥 Deployment on Vercel (like your campus app)

Vercel doesn't support Flask natively, but you can:

### Option A: Vercel + Serverless (recommended for free tier)
1. Add `vercel.json`:
```json
{
  "builds": [{"src": "backend/app.py", "use": "@vercel/python"}],
  "routes": [{"src": "/(.*)", "dest": "backend/app.py"}]
}
```
2. Use **Vercel Postgres** (free) instead of SQLite:
   - `pip install psycopg2-binary`
   - Replace `sqlite3` calls with `psycopg2`

### Option B: Railway.app (easiest, supports SQLite)
```bash
railway login
railway init
railway up
```
Free tier: 500 hours/month — perfect for MVP.

### Option C: Render.com (free Flask hosting)
1. Connect GitHub repo
2. Build command: `pip install -r requirements.txt`
3. Start command: `python backend/app.py`
4. Add `PORT` env var → Render auto-assigns

---

## 📱 MVP Demo Flow (for presentation)

1. Open app → Register with phone + PIN
2. Tap **Book a Drop** → select *Vashi Station* → pick *9:30*
3. System confirms, shows OSRM route, simulates driver assignment
4. Open `/admin` → see booking in group, assign vehicle, reschedule
5. Open `/driver` → see ordered stop list

---

## 🛠️ Next Steps to Extend

| Feature | What to add |
|---|---|
| Real-time driver tracking | WebSockets (Flask-SocketIO) or Firebase |
| Push notifications | Firebase Cloud Messaging |
| Live ETA | OSRM + driver GPS polling |
| Saved locations UI | Already in DB + API, add to chat flow |
| PostgreSQL | Replace sqlite3 with psycopg2, same schema |
| WhatsApp bot | Twilio API → same booking endpoints |
| Payment | Razorpay integration for ride credits |

---

## 🗺️ Navi Mumbai Locations Covered

```
Ostello Parsik Hill (home base)   19.0176, 73.0360
CBD Belapur Station               19.0213, 73.0386
Vashi Station                     19.0730, 72.9987
Kharghar Station                  19.0471, 73.0697
Panvel Station                    18.9894, 73.1175
Seawoods Station                  19.0043, 73.0175
Nerul Station                     19.0363, 73.0175
DY Patil College                  19.0440, 73.0705
NMIMS Navi Mumbai                 19.0430, 73.0200
Inorbit Mall Vashi                19.0630, 73.0049
Mindspace Airoli                  19.1490, 72.9975
Navi Mumbai Airport (future)      18.9953, 73.1289
```
