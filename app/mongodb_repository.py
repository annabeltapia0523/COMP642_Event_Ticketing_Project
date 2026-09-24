from __future__ import annotations

import os
from typing import Any

from pymongo import MongoClient, ReturnDocument
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import PyMongoError


class EventContentError(Exception):
    pass


class MongoDBRepository:

    def __init__(
        self,
        client: MongoClient,
        database: Database,
        collection: Collection,
    ) -> None:
        self._client = client
        self._database = database
        self._collection = collection

    @classmethod
    def from_env(cls) -> "MongoDBRepository":
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass

        uri = os.getenv("MONGODB_URI")

        if not uri:
            raise EventContentError(
                "MONGODB_URI is missing from the environment"
            )

        database_name = os.getenv(
            "MONGODB_DATABASE",
            "event_ticketing_db",
        )

        collection_name = os.getenv(
            "MONGODB_COLLECTION",
            "event_content",
        )

        try:
            client = MongoClient(
                uri,
                serverSelectionTimeoutMS=5000,
            )

            client.admin.command("ping")

            database = client[database_name]
            collection = database[collection_name]

            return cls(
                client,
                database,
                collection,
            )

        except PyMongoError as exc:
            raise EventContentError(
                f"MongoDB connection failed: {exc}"
            ) from exc

    def close(self) -> None:
        self._client.close()

    def list_event_content(self) -> list[dict[str, Any]]:
        try:
            return list(
                self._collection.find(
                    {},
                    {"_id": 0},
                ).sort("eventId", 1)
            )
        except PyMongoError as exc:
            raise EventContentError(
                f"Unable to retrieve event content: {exc}"
            ) from exc

    def get_event_content(
        self,
        event_id: int,
    ) -> dict[str, Any] | None:
        try:
            return self._collection.find_one(
                {"eventId": int(event_id)},
                {"_id": 0},
            )
        except PyMongoError as exc:
            raise EventContentError(
                f"Unable to retrieve event {event_id}: {exc}"
            ) from exc

    def find_events_by_tag(
        self,
        tag: str,
    ) -> list[dict[str, Any]]:
        try:
            return list(
                self._collection.find(
                    {"tags": tag},
                    {"_id": 0},
                ).sort("eventId", 1)
            )
        except PyMongoError as exc:
            raise EventContentError(
                f"Unable to search for tag {tag}: {exc}"
            ) from exc

    def add_review(
        self,
        event_id: int,
        user_id: int,
        rating: int,
        comment: str,
    ) -> dict[str, Any]:
        if rating < 1 or rating > 5:
            raise EventContentError(
                "Rating must be between 1 and 5"
            )

        if not comment.strip():
            raise EventContentError(
                "Review comment cannot be empty"
            )

        review = {
            "userId": int(user_id),
            "rating": int(rating),
            "comment": comment.strip(),
        }

        try:
            updated_event = self._collection.find_one_and_update(
                {"eventId": int(event_id)},
                {"$push": {"reviews": review}},
                projection={"_id": 0},
                return_document=ReturnDocument.AFTER,
            )
        except PyMongoError as exc:
            raise EventContentError(
                f"Unable to add review: {exc}"
            ) from exc

        if updated_event is None:
            raise EventContentError(
                f"Event {event_id} does not exist"
            )

        return updated_event


if __name__ == "__main__":
    repository = MongoDBRepository.from_env()

    try:
        print(
            "Event 101:",
            repository.get_event_content(101),
        )

        print(
            "Number of MongoDB events:",
            len(repository.list_event_content()),
        )
    finally:
        repository.close()
