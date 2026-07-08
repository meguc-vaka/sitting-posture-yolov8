
    DROP TABLE IF EXISTS users;
    CREATE TABLE users (
        userId INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        isAdmin INTEGER DEFAULT 0
    );
    