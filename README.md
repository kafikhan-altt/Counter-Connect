# CounterConnect (Localo)

Cross-counter pre-ordering for independent food courts and local markets.

## Setup Instructions

1. **Activate virtual environment:**

   ```bash
   .\venv\Scripts\activate   # Windows
   # or source venv/bin/activate  (Linux/macOS)
   ```
2. **Install dependencies:**

   ```bash
   pip install django segno
   ```
3. **Run database migrations:**

   ```bash
   python manage.py migrate
   ```
4. **Seed demo data:**

   ```bash
   python manage.py seed_demo
   ```
5. **Start development server:**

   ```bash
   python manage.py runserver
   ```

## Demo Credentials (DEMO ONLY)

- **Admin Portal (`/admin/`):**

  - Username: `admin`
  - Password: `demo12345`
- **Vendor Logins (`/vendor/login/`):**

  - South Indian Corner: `vendor_south` / `demo12345`
  - Chinese Wok: `vendor_chinese` / `demo12345`
  - Juice & Shakes: `vendor_juice` / `demo12345`
  - Bakery & Desserts: `vendor_bakery` / `demo12345`

## Running Automated Tests

```bash
python manage.py test
```
