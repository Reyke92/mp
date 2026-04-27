# Marketplace Website

A Django-based marketplace web application built for an academic software engineering capstone project.

The project models a browser-based marketplace where users can browse listings, search and filter results, message sellers, report inappropriate content, and use role-restricted moderation and administration tools. The scope is intentionally limited to local development and academic evaluation, with cash-only, offline exchanges and no payment processing.

## Overview

Marketplace Website is a server-rendered Django application that supports:

- Public browsing of marketplace listings
- Account registration, login, logout, and profile management
- Listing creation, editing, deletion, image management, and category-specific attributes
- Search, filtering, sorting, and category-based discovery
- Buyer–seller messaging
- Listing and conversation reporting
- Moderation queue and report review workflows
- Administrator dashboards, logs, and oversight pages
- Limited operational analytics such as listing view counts and summary reporting

The application is organized into feature-focused Django apps:

- `accounts` – registration, authentication, profiles, and role-aware account behavior
- `admin_ops` – administrator-only oversight, enforcement, logs, dashboard, and management pages
- `catalog` – categories, conditions, and attribute definitions
- `core` – homepage behavior, shared context, and base site functionality
- `listings` – listing lifecycle, listing detail, seller tools, and listing images
- `messaging` – inbox, conversations, and buyer–seller message flows
- `moderation` – moderation queue, report review, and disposition handling
- `reports` – report submission and report persistence
- `search` – search results, filters, and browse behavior
- `tracking` – listing view counts and derived metadata snapshot support

## Tech Stack

- **Backend:** Django
- **Language:** Python
- **Database:** MySQL
- **Forms/UI:** Django Crispy Forms + crispy-bootstrap5
- **Frontend styling:** Bootstrap 5, project CSS, and server-rendered HTML templates
- **Media support:** Pillow
- **Environment configuration:** `python-dotenv`
- **Database driver:** `mysqlclient`

## Project Characteristics

- Server-rendered web application
- Responsive Bootstrap-based interface
- Role-aware pages for Guests, Authenticated Users, Moderators, and Administrators
- Local-host development target rather than public commercial deployment
- No payments, escrow, refunds, or marketplace-managed transactions
- U.S.-focused scope

## Repository Structure

```text
mp/
├── accounts/
├── admin_ops/
├── catalog/
├── common/
├── core/
├── listings/
├── marketplace/
├── messaging/
├── moderation/
├── reports/
├── search/
├── static/
├── templates/
├── tests/
├── tracking/
├── manage.py
├── requirements.txt
└── Additional Windows Requirements.txt
```

## Getting Started

### 1. Prerequisites

Recommended local environment:

- Python 3.14
- MySQL 8.4 LTS
- A modern web browser

Windows users should also review:

- `Additional Windows Requirements.txt`

### 2. Clone the repository

```bash
git clone https://github.com/Reyke92/mp.git
cd mp
```

### 3. Create and activate a virtual environment

#### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

#### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure the database

Create a MySQL database for the project and supply connection settings through environment variables.

Example values used by the project settings:

```env
DB_NAME=mp
DB_USER=dbadmin
DB_PASSWORD=Secure_db_admin_password16
DB_HOST=localhost
DB_PORT=3306
```

You can place these in a local `.env` file if desired.

### 6. Run migrations

```bash
python manage.py migrate
```

### 7. Collect static files

```bash
python manage.py collectstatic --noinput
```

### 8. Start the development server

```bash
python manage.py runserver
```

Then open the app in your browser.

## Important Database Note

This project is configured to support real records with `ID = 0` where applicable.

The Django database configuration initializes the MySQL session with:

```sql
SET SESSION sql_mode = CONCAT(@@SESSION.sql_mode, ',NO_AUTO_VALUE_ON_ZERO');
```

That behavior is already set in `marketplace/settings.py`, but it is worth remembering when working with imports, seed data, or debugging identity behavior.

## Running Tests

The repository includes automated test coverage organized by test level.

### Run the full Django test suite

```bash
python manage.py test
```

### Run specific test groups

```bash
python manage.py test tests.unit
python manage.py test tests.integration
python manage.py test tests.security
python manage.py test tests.system
python manage.py test tests.ui
python manage.py test tests.performance
```

### Test organization

```text
tests/
├── unit/
├── integration/
├── security/
├── system/
├── ui/
└── performance/
```

The project also uses GitHub Actions for CI-based test execution.

## Core Workflows

### Standard user flows

- Register an account
- Log in and manage a profile
- Browse and search listings
- Create, edit, and manage listings
- Message sellers
- Submit reports for listings or conversations

### Moderator flows

- Access the moderation queue
- Review report details
- Record moderation dispositions
- Review related recent reports for the same target

### Administrator flows

- Access the admin dashboard
- Manage users and listings
- Review moderation and administration logs
- Review conversation oversight pages
- Use reports hub and summary pages

## Static and Media Files

The project serves static and media files through Django in local development. After changing CSS or other static assets, it is a good idea to run:

```bash
python manage.py collectstatic --noinput
```

## Development Notes

- This project is intended for local development and academic evaluation.
- The database is MySQL-based, not SQLite.
- The interface is server-rendered with Django templates and Bootstrap components.
- The application includes custom 403, 404, and 500 error pages.
- Role-restricted pages are enforced in the application layer.

## Contributors

- Josiah Ferguson
- Elijah Brooks
- Michael Goldsmith

## Academic Context

This repository was developed as part of a software engineering capstone project. The implementation focuses on correctness, maintainability, documentation alignment, and role-aware marketplace workflows rather than public-production deployment concerns.
