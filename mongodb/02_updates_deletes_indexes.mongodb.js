use("event_ticketing_db");

const eventCollection = db.getCollection("event_content");

const eventIdIndex = eventCollection.createIndex(
    {
        eventId: 1
    },
    {
        unique: true,
        name: "eventId_unique"
    }
);

const tagsIndex = eventCollection.createIndex(
    {
        tags: 1
    },
    {
        name: "tags_index"
    }
);

const eventUpdate = eventCollection.updateOne(
    {
        eventId: 105
    },
    {
        $set: {
            skillLevel: "Beginner-Friendly",
            "requirements.registrationRequired": true
        },
        $addToSet: {
            tags: "Hands-On"
        }
    }
);

const reviewUpdate = eventCollection.updateOne(
    {
        eventId: 102
    },
    {
        $addToSet: {
            reviews: {
                userId: 250,
                rating: 5,
                comment: "A fun concert with great music"
            }
        }
    }
);

const temporaryInsert = eventCollection.updateOne(
    {
        eventId: 999
    },
    {
        $setOnInsert: {
            eventId: 999,
            title: "Temporary Test Event",
            eventType: "Test Event",
            description: "Temporary document used to demonstrate deletion."
        }
    },
    {
        upsert: true
    }
);

const temporaryDelete = eventCollection.deleteOne(
    {
        eventId: 999
    }
);

const remainingTemporaryDocuments = eventCollection.countDocuments(
    {
        eventId: 999
    }
);

const updatedEvents = eventCollection
    .find(
        {
            eventId: {
                $in: [
                    102,
                    105
                ]
            }
        },
        {
            _id: 0,
            eventId: 1,
            title: 1,
            tags: 1,
            skillLevel: 1,
            requirements: 1,
            reviews: 1
        }
    )
    .sort({
        eventId: 1
    })
    .toArray();

const collectionIndexes = eventCollection.getIndexes();

({
    eventIdIndex,
    tagsIndex,
    eventUpdate,
    reviewUpdate,
    temporaryInsert,
    temporaryDelete,
    remainingTemporaryDocuments,
    updatedEvents,
    collectionIndexes
});