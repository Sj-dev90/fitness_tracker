# Cloud-Native Fitness & Workout Tracker

[![Live Demo](https://img.shields.io/badge/Live_Demo-View_Website-3b82f6?style=for-the-badge)](https://fitness-tracker-wqcd.onrender.com)

A cloud-hosted, three-tier CRUD application designed to help athletes and fitness enthusiasts track their strength progression. This project replaces unstructured, localized phone notes with a centralized database, ensuring workout data (sets, reps, weight) is securely stored, easily accessible, and globally available.

**Developed as a Challenging Digital Assignment.**

---

## 🚀 Live Deployment
The application is fully containerized and deployed on Render. 
**Access the live web app here:** [https://fitness-tracker-wqcd.onrender.com](https://fitness-tracker-wqcd.onrender.com)

---

## 🛠️ Tech Stack & Architecture

This project utilizes a modern, decoupled three-tier architecture:

* **Frontend (Presentation Layer):** Vanilla HTML5, CSS3, and JavaScript. Features a data-heavy, modern dashboard aesthetic with zero heavy framework dependencies.
* **Backend (Application Layer):** Python / Flask. Acts as the RESTful API server handling HTTP requests and business logic.
* **Database (Data Layer):** MongoDB Atlas (Cloud NoSQL). Ensures state persistence and high availability across server environments.
* **Deployment & Hosting:** Git, GitHub, Render, Gunicorn.

---

## ✨ Key Features

* **Complete CRUD Functionality:** Users can seamlessly Create, Read, Update, and Delete workout entries via decoupled REST API endpoints.
* **Cloud Persistence:** Data is reliably stored on a MongoDB Atlas cluster, surviving local device loss and server restarts.
* **Modern UI/UX:** A crisp, professional interface inspired by modern health dashboards.
* **Dynamic Theme Toggling:** A Vanilla JS and CSS variable-driven Light/Dark mode switch that saves user preferences locally via `localStorage`.
* **Fully Responsive:** Layout adapts gracefully from desktop monitors to mobile screens.

---

## 💻 Local Installation & Setup

If you wish to run this application locally, follow these steps:

**1. Clone the repository:**
```bash
git clone [https://github.com/Sj-dev90/fitness_tracker.git](https://github.com/Sj-dev90/fitness_tracker.git)
cd fitness_tracker
2. Install dependencies:

Bash
pip install -r requirements.txt
3. Configure Environment Variables:
Create a .env file in the root directory and add your MongoDB Atlas connection string:

Code snippet
MONGO_URI=mongodb+srv://<username>:<password>@cluster0.example.mongodb.net/fitness_tracker?retryWrites=true&w=majority
4. Run the application:

Bash
python app.py
The app will be available at http://localhost:5000

👨‍💻 Author
Siddharth Jain

B.Tech Computer Science and Engineering (CSE Core)

VIT Chennai
