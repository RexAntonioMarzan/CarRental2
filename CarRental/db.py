# db.py  (MySQL / XAMPP version)

import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash

DB_NAME = "car_rent"

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "port": 3306,
}


def get_db():
    """
    Open a connection to the MySQL database.
    Ginagamit sa app.py: conn = get_db()
    Then: cursor = conn.cursor(dictionary=True)
    """
    conn = mysql.connector.connect(database=DB_NAME, **DB_CONFIG)
    return conn


def seed_cars(cursor):
    """
    Insert / update sample cars.
    - Kung wala pa yung car name -> INSERT
    - Kung meron na -> UPDATE car_type, price, image_url
    para mapalitan yung luma mong Unsplash URLs.
    """
    cars = [
        ("Toyota Vios", "Sedan", 1800, "images/Toyota Vios.jpg"),
        ("Honda Civic", "Sedan", 2100, "images/Honda Civic.jpg"),
        ("Toyota Camry", "Sedan", 2700, "images/Toyota Camry.jpg"),
        ("Nissan Almera", "Sedan", 1700, "images/Nissan Almera.jpg"),
        ("Honda BR-V", "MPV", 2300, "images/Honda BR-V.jpg"),
        ("Suzuki Ertiga", "MPV", 2150, "images/Suzuki Ertiga.jpg"),
        ("Toyota Innova", "MPV", 2600, "images/Toyota Innova.jpg"),
        ("Hyundai Staria", "Van", 3400, "images/Hyundai Staria.jpg"),
        ("Mitsubishi L300", "Van", 3000, "images/Mitsubishi L300.jpg"),
        ("Toyota Hiace", "Van", 3200, "images/Toyota Hiace.jpg"),
        ("Ford Ranger", "Pickup", 3500, "images/Ford Ranger.jpg"),
        ("Nissan Navara", "Pickup", 3350, "images/Nissan Navara.jpg"),
        ("Isuzu D-Max", "Pickup", 3300, "images/Isuzu D-Max.jpg"),
        ("Toyota Fortuner", "SUV", 3600, "images/Toyota Fortuner.jpg"),
        ("Ford Everest", "SUV", 3700, "images/Ford Everest.jpg"),
        ("Mazda CX-5", "SUV", 2800, "images/Mazda CX-5.jpg"),
        ("Honda CR-V", "SUV", 2950, "images/Honda CR-V.jpg"),
        ("Subaru Forester", "SUV", 3100, "images/Subaru Forester.jpg"),
        ("BMW 3 Series", "Sedan", 5200, "images/BMW 3 Series.jpg"),
        ("Mercedes-Benz GLC", "SUV", 6000, "images/Mercedes-Benz GLC.jpg"),
    ]

    for name, car_type, price, image_url in cars:
        # check kung existing na by name
        cursor.execute("SELECT id FROM cars WHERE name = %s", (name,))
        row = cursor.fetchone()

        if row:
            # UPDATE existing row (para mapalitan yung luma mong URL)
            car_id = row[0]
            cursor.execute(
                """
                UPDATE cars
                SET car_type = %s,
                    price_per_day = %s,
                    image_url = %s
                WHERE id = %s
                """,
                (car_type, price, image_url, car_id),
            )
        else:
            # INSERT new row
            cursor.execute(
                """
                INSERT INTO cars (name, car_type, price_per_day, image_url)
                VALUES (%s, %s, %s, %s)
                """,
                (name, car_type, price, image_url),
            )


def init_db():
    """
    Gumagawa ng database + tables + admin user + sample cars.
    Tatawagin sa app.py bago mag app.run().
    """
    # 1) Create database if not exists
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute(
        f"CREATE DATABASE IF NOT EXISTS {DB_NAME} "
        "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    conn.commit()
    cursor.close()
    conn.close()

    # 2) Create tables inside that DB
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            car_id INT NOT NULL,
            days INT NOT NULL,
            total_price DECIMAL(10,2) NOT NULL,

            -- trip timing
            pickup_at DATETIME NOT NULL,
            return_at DATETIME NOT NULL,

            -- add-ons
            addon_child_seat TINYINT(1) DEFAULT 0,
            addon_toll_rfid TINYINT(1) DEFAULT 0,
            addon_dashcam TINYINT(1) DEFAULT 0,

            -- discounts
            discount_applied TINYINT(1) DEFAULT 0,
            discount_type VARCHAR(20),
            discount_rate DECIMAL(5,2) DEFAULT 0.00,
            discount_amount DECIMAL(10,2) DEFAULT 0.00,

            -- uploaded files
            license_file VARCHAR(255),
            discount_id_file VARCHAR(255),

            -- payment info
            payment_status VARCHAR(20) DEFAULT 'pending',
            payment_provider VARCHAR(50),
            payment_ref VARCHAR(100),

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (car_id) REFERENCES cars(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS cars (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            car_type VARCHAR(50) NOT NULL,
            price_per_day DECIMAL(10,2) NOT NULL,
            image_url VARCHAR(255)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            car_id INT,
            days INT,
            total_price DECIMAL(10,2),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (car_id) REFERENCES cars(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
    )

    # 3) Ensure may 1 admin user
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
    row = cursor.fetchone()
    count = row[0] if row else 0
    if count == 0:
        cursor.execute(
            """
            INSERT INTO users (username, email, password, is_admin)
            VALUES (%s, %s, %s, 1)
            """,
            ("admin", "admin@example.com", generate_password_hash("admin123")),
        )

    # 4) Seed / update cars
    seed_cars(cursor)

    conn.commit()
    cursor.close()
    conn.close()