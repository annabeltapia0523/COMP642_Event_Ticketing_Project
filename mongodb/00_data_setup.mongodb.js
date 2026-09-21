use("event_ticketing_db");

db.getCollection("event_content").deleteMany({});

db.getCollection("event_content").insertOne({
    eventId: 101,
    title: "AI and Data Science Conference",
    eventType: "Conference",
    description: "A conference about current developments in artificial intelligence and data science.",

    tags: [
        "AI",
        "Data Science",
        "Machine Learning"
    ],

    speakers: [
        {
            name: "Maria Chen",
            organization: "TechAI",
            topics: [
                "Generative AI",
                "RAG"
            ]
        },
        {
            name: "Daniel Ruiz",
            organization: "DataWorks",
            topics: [
                "Predictive Analytics",
                "Data Ethics"
            ]
        }
    ],

    schedule: [
        {
            time: "09:00",
            session: "Opening Keynote",
            room: "Grand Ballroom"
        },
        {
            time: "11:00",
            session: "Building Reliable AI Systems",
            room: "Room A"
        }
    ],

    reviews: [
        {
            userId: 204,
            rating: 5,
            comment: "Excellent conference"
        },
        {
            userId: 209,
            rating: 4,
            comment: "Very informative sessions"
        }
    ]
});

db.getCollection("event_content").insertMany([
    {
        eventId: 102,
        title: "Summer Beats Concert",
        eventType: "Concert",
        description: "An outdoor evening concert featuring popular local artists.",

        performers: [
            "Luna Ray",
            "The Echoes"
        ],

        genres: [
            "Pop",
            "Alternative"
        ],

        ageRestriction: 16,

        production: {
            outdoor: true,
            doorsOpen: "17:30"
        },

        reviews: [
            {
                userId: 211,
                rating: 5,
                comment: "Amazing performances"
            },
            {
                userId: 215,
                rating: 4,
                comment: "Great outdoor venue"
            }
        ]
    },

    {
        eventId: 103,
        title: "City Hawks Championship Game",
        eventType: "Sporting Event",
        description: "The City Hawks compete in the regional basketball championship.",

        sport: "Basketball",

        teams: [
            {
                name: "City Hawks",
                role: "Home"
            },
            {
                name: "Valley Bears",
                role: "Away"
            }
        ],

        gameDetails: {
            season: "2026",
            round: "Championship",
            gatesOpen: "17:00"
        },

        reviews: [
            {
                userId: 218,
                rating: 4,
                comment: "Exciting game"
            }
        ]
    },

    {
        eventId: 104,
        title: "CSUN Graduate Research Showcase",
        eventType: "University Event",
        description: "Graduate students present research projects from several academic departments.",

        departments: [
            "Computer Science",
            "Engineering",
            "Health Sciences"
        ],

        presenters: [
            {
                name: "Elena Torres",
                project: "Machine Learning for Public Health"
            },
            {
                name: "Kevin Patel",
                project: "Smart Energy Monitoring"
            }
        ],

        admission: {
            students: "Free",
            generalPublic: 10
        },

        reviews: [
            {
                userId: 221,
                rating: 5,
                comment: "The student projects were impressive"
            }
        ]
    },

    {
        eventId: 105,
        title: "Python for Data Analytics Workshop",
        eventType: "Workshop",
        description: "A hands-on workshop covering Python, pandas, and data visualization.",

        tags: [
            "Python",
            "Data Analytics",
            "Programming"
        ],

        instructors: [
            {
                name: "Sophia Martinez",
                specialty: "Data Science"
            }
        ],

        skillLevel: "Beginner",

        materials: [
            "Laptop",
            "Python",
            "Jupyter Notebook"
        ],

        requirements: {
            laptopRequired: true,
            priorExperienceRequired: false
        },

        reviews: [
            {
                userId: 225,
                rating: 5,
                comment: "Easy to follow and very useful"
            },
            {
                userId: 227,
                rating: 4,
                comment: "Good beginner workshop"
            }
        ]
    },

    {
        eventId: 106,
        title: "Santa Clarita Food and Arts Festival",
        eventType: "Community Event",
        description: "A family festival featuring food, art, music, and community activities.",

        tags: [
            "Food",
            "Art",
            "Family"
        ],

        vendors: [
            {
                name: "Valley Tacos",
                category: "Food"
            },
            {
                name: "Local Canvas",
                category: "Art"
            }
        ],

        activities: [
            "Live Music",
            "Art Displays",
            "Children's Activities"
        ],

        familyFriendly: true,

        reviews: [
            {
                userId: 230,
                rating: 4,
                comment: "Fun activities for the whole family"
            }
        ]
    },

    {
        eventId: 107,
        title: "Cybersecurity Leadership Conference",
        eventType: "Conference",
        description: "Industry leaders discuss cybersecurity risks and protection strategies.",

        tags: [
            "Cybersecurity",
            "Technology",
            "Leadership"
        ],

        speakers: [
            {
                name: "Jordan Lee",
                organization: "SecureNet",
                topics: [
                    "Cloud Security",
                    "Risk Management"
                ]
            },
            {
                name: "Alicia Gomez",
                organization: "Cyber Defense Group",
                topics: [
                    "Incident Response"
                ]
            }
        ],

        schedule: [
            {
                time: "10:00",
                session: "Modern Security Risks",
                room: "Conference Hall"
            },
            {
                time: "13:00",
                session: "Incident Response Planning",
                room: "Room B"
            }
        ],

        reviews: [
            {
                userId: 233,
                rating: 3,
                comment: "Useful information but limited networking time"
            }
        ]
    },

    {
        eventId: 108,
        title: "Rock Under the Stars",
        eventType: "Concert",
        description: "A nighttime rock concert featuring regional bands.",

        performers: [
            "Midnight Drive",
            "The Canyon Lights"
        ],

        genres: [
            "Rock",
            "Classic Rock"
        ],

        ageRestriction: 18,

        production: {
            outdoor: true,
            doorsOpen: "18:00"
        },

        reviews: [
            {
                userId: 236,
                rating: 5,
                comment: "The bands were fantastic"
            }
        ]
    },

    {
        eventId: 109,
        title: "Beginner Photography Workshop",
        eventType: "Workshop",
        description: "A beginner workshop covering camera settings and photo composition.",

        tags: [
            "Photography",
            "Art",
            "Beginner"
        ],

        instructors: [
            {
                name: "Rachel Kim",
                specialty: "Portrait Photography"
            }
        ],

        skillLevel: "Beginner",
        durationHours: 3,

        materials: [
            "Digital Camera",
            "Memory Card",
            "Notebook"
        ],

        reviews: [
            {
                userId: 239,
                rating: 4,
                comment: "Helpful practice exercises"
            }
        ]
    },

    {
        eventId: 110,
        title: "Community Charity 5K Run",
        eventType: "Sporting Event",
        description: "A community run that raises funds for local youth programs.",

        sport: "Running",

        categories: [
            "Adult",
            "Teen",
            "Family Walk"
        ],

        route: {
            distanceKilometers: 5,
            waterStations: 3,
            startLocation: "Central Park"
        },

        requirements: {
            minimumAge: 10,
            waiverRequired: true
        },

        reviews: [
            {
                userId: 242,
                rating: 5,
                comment: "Well organized and supported a great cause"
            }
        ]
    }
]);

db.getCollection("event_content")
    .find(
        {},
        {
            _id: 0,
            eventId: 1,
            title: 1,
            eventType: 1
        }
    )
    .sort({
        eventId: 1
    });