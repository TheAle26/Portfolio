
<a href="README-es.md">🇪🇸 Leer en Español</a> | 🇬🇧 English


# Alejo Vincent | Portfolio & Home Server Hub

## About the Project

This repository contains the source code for my interactive personal portfolio. More than just a simple static *landing page*, this project serves as the central node (Hub) for my application ecosystem.

It is developed entirely in *Django* and is hosted and served to the world from a local server (a Raspberry Pi) configured from scratch in my own home. It demonstrates not only my Backend development capabilities but also solid skills in infrastructure, networking, microservices deployment, and DevOps philosophy.

---

## Architecture and Technologies

The system is designed to be resilient, secure, and completely self-contained. The technology stack used for its architecture includes:

* **Backend:** Python + Django
* **Frontend:** HTML5, pure CSS, Bootstrap 5, and FontAwesome. Integrated *template* system for dynamic static file downloads (CV).
* **Database:** PostgreSQL (manages data persistence for the entire ecosystem).
* **Containers:** Docker & Docker Compose to orchestrate the application securely, isolating processes and avoiding execution with root privileges within the application containers.
* **Web Server / Reverse Proxy:** Nginx (manages HTTPS certificates, routes internal traffic, and serves static files).
* **Application Server:** Gunicorn.
* **Infrastructure:** Raspberry Pi running Linux (Debian-based), with SSH security management.
* **Network:** Dynamic DNS (No-IP) for domain routing to a dynamic IP.

---

## 🌐 The Ecosystem (Integrated Projects)

This portfolio documents and provides access to the real applications that make up my development environment. All the code coexists and is orchestrated by this very repository:

### 1. 🛰️ IoT Tracking Dashboard
Real-time telemetry system for logistics fleets.
* **Hardware Integration:** Utilization of Teltonika (FMC150) physical devices via the Flespi platform.
* **Route Simulation:** Live simulation engine processing `.gpx` files and calculating real physical variables (Haversine formula for distances, fuel consumption, voltage).
* **Automated Reports:** Background scheduled tasks using `APScheduler` under the *Catch-Up* pattern to guarantee daily report generation in case of server downtime or power outages (Upcoming feature).

### 2. 💊 FarmaGo
Delivery platform with strict access control.
* **Role Architecture:** Management of three independent entities (Client, Pharmacy, Driver).
* **Security:** Implementation of a customized user model (`Custom User Model`) and strict data validation using Regex.

### 3. ⚽ FulboApp
Comprehensive amateur sports management system.
* Developed in Django, focused on robust relational data modeling and user experience through protected administration panels.

---

## 📬 Contact

Interested in my profile for a formal first experience in the IT sector as a Trainee/Junior? Let's talk!

* **Email:** alejo.vincent26@gmail.com
* **LinkedIn:** [Alejo Vincent](https://www.linkedin.com/in/alejo-vincent-37aa63220/)
* **GitHub:** [@TheAle26](https://github.com/TheAle26)