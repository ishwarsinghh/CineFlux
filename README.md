# 🎬 CineFlux

A highly scalable, high-concurrency Movie Ticket Reservation System built with Django, Django REST Framework, PostgreSQL, Redis, Celery, and a Vanilla JS Single Page Application (SPA).

## 🚀 Architecture & Features
- **Pessimistic Locking:** Solves the Double Booking problem using Postgres row-level locks (`select_for_update()`).
- **Cache-Aside Pattern:** Utilizes Redis caching for ultra-fast, read-heavy movie showtime queries.
- **Asynchronous Workers:** Implements Celery background tasks to automatically release abandoned seats (The Cart Hoarder problem).
- **Stateless Authentication:** Secure JWT (JSON Web Tokens) integration for scalable, session-less auth.
- **Idempotency:** Webhook processing guaranteed to process only once to prevent double charges.
- **Decoupled Frontend:** Beautiful, responsive UI built with Vanilla JS and Tailwind CSS communicating exclusively via REST APIs.

## 🛠️ Tech Stack
- **Backend:** Python, Django, Django REST Framework (DRF)
- **Database:** PostgreSQL
- **Cache & Message Broker:** Redis
- **Background Tasks:** Celery
- **Frontend:** HTML5, Vanilla JavaScript, Tailwind CSS
- **Infrastructure:** Docker & Docker Compose

## ⚙️ How to Run Locally

### 1. Start Infrastructure (Docker)
Ensure Docker Desktop is running, then start the PostgreSQL database and Redis cache:
```bash
docker-compose up -d
```

### 2. Setup Python Environment
```bash
# Activate virtual environment
source venv/Scripts/activate  # On Windows Git Bash

# Install dependencies
pip install -r requirements.txt
```

### 3. Database Migrations, Superuser & Seeding
```bash
# Apply schema to Postgres
python manage.py makemigrations api
python manage.py migrate

# Create a superuser manually (you will be prompted for a username, email, and password)
python manage.py createsuperuser

# Seed dummy data (Cinemas, Movies, Seats, Showtimes)
python seed.py
```

### 4. Start the Application
```bash
python manage.py runserver
```
Navigate to **http://localhost:8000** in your browser!
