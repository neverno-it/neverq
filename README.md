# NeverQ — Corporate Cafeteria & Food Ordering System

Django 4.2 · Bootstrap 5 · SQLite · Blue/Red Theme

## Quick Start (Windows)

```powershell
# 1. Create virtual environment
python -m venv venv
.\venv\Scripts\Activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy env file and set a SECRET_KEY
copy .env.example .env
# Edit .env and replace the SECRET_KEY placeholder (see instructions inside)

# 4. Apply migrations
python manage.py migrate

# 5. Seed demo data
python manage.py seed_data

# 6. Run server
python manage.py runserver
```

## Quick Start (Linux / Mac)

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Copy env file and set a SECRET_KEY
cp .env.example .env
# Edit .env and replace the SECRET_KEY placeholder (see instructions inside)

python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

## Demo Credentials

These credentials are created by `python manage.py seed_data`.

| Role | Email | Password |
|------|-------|----------|
| Super Admin | admin@neverq.co.in | admin123 |
| Company Admin (Linde) | manager@linde.com | admin123 |
| POS Operator | pos@linde.com | admin123 |
| Chef / Kitchen | chef@linde.com | admin123 |
| Reports | reports@linde.com | admin123 |
| Customer | customer@linde.com | customer123 |

## URLs

| Page | URL |
|------|-----|
| Staff Login | http://127.0.0.1:8000/auth/login/ |
| Customer Login | http://127.0.0.1:8000/auth/customer/login/ |
| Dashboard | http://127.0.0.1:8000/dashboard/ |
| POS Terminal | http://127.0.0.1:8000/pos/ |
| Display Board | http://127.0.0.1:8000/orders/display-board/ |
| Django Admin | http://127.0.0.1:8000/admin/ |

## Production Configuration

Copy `.env.example` to `.env` and edit before deploying.  
See the comments inside `.env.example` for full instructions.

| Variable | Local dev | Production |
|----------|-----------|------------|
| `DEBUG` | `True` | **`False`** |
| `SECRET_KEY` | any string | strong random (see keygen command in `.env.example`) |
| `ALLOWED_HOSTS` | `127.0.0.1,localhost` | your domain(s) |
| `CSRF_TRUSTED_ORIGINS` | not needed | `https://yourdomain.com` |
| `SESSION_COOKIE_SECURE` | `False` | **`True`** (requires HTTPS) |
| `CSRF_COOKIE_SECURE` | `False` | **`True`** (requires HTTPS) |
| `SECURE_SSL_REDIRECT` | `False` | **`True`** (requires HTTPS) |

**Database:** SQLite is used by default and requires no extra setup.  
To switch to PostgreSQL, install `psycopg2` and update the `DATABASES` dict in
`neverq/settings.py` directly — there is no `DATABASE_URL` env var support.

> **Never run `python manage.py makemigrations` on a deployed instance.**  
> Migrations are shipped with the project. Run `migrate` only.

## Project Structure

```
NeverQ/
├── apps/
│   ├── accounts/      # StaffUser, Customer, auth, dashboard views
│   ├── core/          # Company, Building, Coupon, Notification, StaticPage
│   ├── menu/          # Category, Product, Advertise, MediaAsset, HolidaySchedule
│   ├── orders/        # Order, OrderItem, checkout, display board, KOT, kiosk
│   ├── pos/           # POS terminal, POSOrder, receipt
│   └── reviews/       # Customer reviews
├── templates/         # All HTML templates (auth, dashboard, menu, orders, pos, reviews, kiosk)
├── static/            # CSS, JS, images
├── media/             # Uploaded files
├── neverq/            # Django project settings
├── manage.py
├── requirements.txt
└── .env.example       # Copy to .env and fill in before running
```

## Features

### Customer-Facing
- Company-scoped menu browsing with schedule-based availability
- Session-based cart with add/remove/update quantity
- Coupon code application at checkout
- Multiple payment modes (Cash, Online, Monthly, Company billing)
- Order history and real-time status tracking
- Customer reviews and ratings
- Forgot password with OTP
- Static pages (About, Terms, Privacy, Refund, Contact)

### Self-Order Kiosk
- No-login, company-scoped kiosk at `/orders/kiosk/<company_id>/`
- Optional per-kiosk config via `?kiosk=<slug>` (theme, logo, welcome text)
- Building / cafe filter with true session-backed reset
- Offering → Category → Product drill-down
- Veg-only filter
- Counter ticket generation with QR codes
- Bluetooth ESC/POS thermal printing

### Admin Dashboard
- 12 stat cards with today/total web + POS metrics
- Weekly revenue chart (Chart.js)
- Company CRUD (superadmin only) with building management
- Category hierarchy (root → child → sub-child) with scheduling
- Product CRUD with bulk CSV upload
- Advertisement banners with approval workflow
- Media library for reusable images
- Holiday schedule management (recurring annual dates)
- Flash order placement by staff
- CSV export for orders and reports
- Staff user management with 5 roles
- Coupon management (flat/percentage, date range, usage limits)
- Static page management

### Cashier / POS
- Real-time cashier view with status change
- POS terminal with product grid and cart
- Cash/Card/UPI payment types
- POS receipt printing
- KOT (Kitchen Order Ticket) data endpoint

### Kitchen
- Pending → Confirmed → Preparing → Ready workflow
- Order cards with item details

### Operations
- Live display board (public, auto-refreshing)
- Notification system (bell icon, AJAX polling)
- Auto order status management command (cron-ready)
- Store open/close toggle

## Management Commands

```bash
# Seed demo data
python manage.py seed_data
python manage.py seed_data --flush  # wipe + re-seed

# Reset admin password
python manage.py reset_admin

# Auto-update stale orders (run via cron)
python manage.py auto_order_status
python manage.py auto_order_status --cancel-after 4 --deliver-after 2
python manage.py auto_order_status --dry-run
```

## Upgrade Roadmap

### Phase 1 — Immediate
- [ ] Payment gateway integration (Razorpay recommended)
- [ ] Email service (SendGrid/SMTP) for OTP, order confirmations
- [ ] PDF receipt/bill generation (ReportLab)

### Phase 2 — Near-term
- [ ] WhatsApp notifications (Twilio/Interakt API)
- [ ] Google/Facebook social login (django-allauth)
- [ ] Celery + Redis for background tasks
- [ ] Real-time WebSocket for kitchen display (Django Channels)

### Phase 3 — Growth
- [ ] Mobile app API (Django REST Framework)
- [ ] Multi-language support (i18n)
- [ ] Analytics dashboard with advanced charts
- [ ] Inventory management system
- [ ] Employee wallet/prepaid balance system
- [ ] QR code table ordering
- [ ] Kitchen display system (KDS) with touch interface
- [ ] PostgreSQL migration for production
