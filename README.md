# 🎬 CineFlux

A highly scalable, high-concurrency Movie Ticket Reservation System built with Django, Django REST Framework, PostgreSQL, Redis, Celery, Django Channels (WebSockets), and a Vanilla JS Single Page Application (SPA).

## 🚀 Architecture & Features

- **Pessimistic Locking (Double Booking Prevention):** Leverages Postgres row-level locks (`select_for_update()`) within database transactions to ensure atomic seat reservations under high concurrency, completely eliminating double-booking edge cases.
- **Real-Time Seat Availability (WebSockets):** Implements Django Channels and ASGI to push live, bi-directional seat status updates to all connected clients instantly without polling, preventing users from selecting seats that just became locked.
- **Asynchronous Background Workers:** Offloads heavy I/O tasks (email confirmations) and periodic background jobs (releasing abandoned "Cart Hoarder" seats) to Celery with Redis as the message broker, drastically improving API response times.
- **Cache-Aside Pattern:** Employs Redis caching for read-heavy endpoints (e.g., movie schedules and showtimes) to reduce database load and provide sub-millisecond read latency.
- **Idempotency & Webhook Processing:** Implements idempotent webhook handlers for payment processing, guaranteeing that webhooks process only once to prevent duplicate charges in distributed systems.
- **Stateless Authentication:** Utilizes secure JWT (JSON Web Tokens) for scalable, session-less authentication across the decoupled architecture.
- **Decoupled Architecture:** Features a standalone frontend SPA built with Vanilla JS and Tailwind CSS that communicates with the backend exclusively via REST APIs and WebSockets.

## 🛠️ Tech Stack

- **Backend:** Python, Django, Django REST Framework (DRF)
- **Real-Time:** Django Channels, Daphne, ASGI
- **Database:** PostgreSQL
- **Cache & Message Broker:** Redis
- **Background Tasks:** Celery, Celery Beat
- **Frontend:** HTML5, Vanilla JavaScript, Tailwind CSS
- **Infrastructure:** Docker & Docker Compose

