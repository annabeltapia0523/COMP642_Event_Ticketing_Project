# COMP642_Event_Ticketing_Project

Event ticketing database project using MySQL, MongoDB, Redis, Python, and FastAPI.

## Application Integration

FastAPI provides the REST API layer connecting MySQL, MongoDB, and Redis.

### Run the API

Install dependencies:

pip install -r requirements.txt

Make sure MySQL, MongoDB, and Redis connection settings are configured
in a local `.env` file and Redis is running.

Start the API:

uvicorn app.main:app --reload

Then open the Swagger documentation:

http://127.0.0.1:8000/docs

Note: MongoDB Atlas may require the user's current IP address to be
allowed in Atlas Network Access.

## Databases

- MySQL — users, events, ticket inventory, orders, and payments
- MongoDB — flexible event content and reviews
- Redis — event caching and trending events
