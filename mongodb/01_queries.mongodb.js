use("event_ticketing_db");

db.getCollection("event_content").find(
    {
        tags: "AI"
    },
    {
        _id: 0,
        eventId: 1,
        title: 1,
        tags: 1
    }
);

db.getCollection("event_content").find(
    {
        "speakers.name": "Maria Chen"
    },
    {
        _id: 0,
        eventId: 1,
        title: 1,
        speakers: 1
    }
);

db.getCollection("event_content").find(
    {
        "reviews.rating": {
            $gt: 4
        }
    },
    {
        _id: 0,
        eventId: 1,
        title: 1,
        "reviews.rating": 1
    }
);

db.getCollection("event_content").find(
    {
        $and: [
            {
                eventType: "Concert"
            },
            {
                ageRestriction: {
                    $gte: 18
                }
            },
            {
                "production.outdoor": true
            }
        ]
    },
    {
        _id: 0,
        eventId: 1,
        title: 1,
        eventType: 1,
        ageRestriction: 1,
        production: 1
    }
);

db.getCollection("event_content").find(
    {
        $or: [
            {
                eventType: "Workshop"
            },
            {
                eventType: "University Event"
            }
        ]
    },
    {
        _id: 0,
        eventId: 1,
        title: 1,
        eventType: 1
    }
);

db.getCollection("event_content").find(
    {
        reviews: {
            $elemMatch: {
                rating: 5,
                userId: {
                    $gte: 230
                }
            }
        }
    },
    {
        _id: 0,
        eventId: 1,
        title: 1,
        reviews: 1
    }
);

db.getCollection("event_content").find(
    {
        schedule: {
            $elemMatch: {
                time: "13:00",
                room: "Room B"
            }
        }
    },
    {
        _id: 0,
        eventId: 1,
        title: 1,
        schedule: 1
    }
);

db.getCollection("event_content").find(
    {
        eventType: "Concert",
        genres: "Rock"
    },
    {
        _id: 0,
        eventId: 1,
        title: 1,
        genres: 1
    }
);