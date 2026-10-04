# COMP642_Event_Ticketing_Project

Event ticketing database project using MySQL, MongoDB, Redis, Python, and FastAPI.

## Application Integration

FastAPI provides the REST API layer connecting MySQL, MongoDB, and Redis.

### Run the API

Install dependencies:

pip install -r requirements.txt

Start FastAPI:

uvicorn app.main:app --reload

Then open the Swagger API documentation at:

http://127.0.0.1:8000/docs

## Databases

- MySQL — users, events, ticket inventory, orders, and payments
- MongoDB — flexible event content and reviews
- Redis — event caching and trending events
