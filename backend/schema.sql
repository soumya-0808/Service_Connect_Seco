CREATE DATABASE IF NOT EXISTS serviceconnect_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE serviceconnect_db;

CREATE TABLE users (
 user_id INT AUTO_INCREMENT PRIMARY KEY, full_name VARCHAR(120) NOT NULL,
 email VARCHAR(255) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL,
 phone VARCHAR(30), role ENUM('customer','provider','admin') NOT NULL DEFAULT 'customer',
 is_active BOOLEAN NOT NULL DEFAULT TRUE, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 INDEX ix_users_email(email)
) ENGINE=InnoDB;
CREATE TABLE provider_profiles (
 provider_id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NOT NULL UNIQUE,
 business_name VARCHAR(160) NOT NULL, description TEXT, city VARCHAR(100),
 experience_years INT NOT NULL DEFAULT 0, is_approved BOOLEAN NOT NULL DEFAULT FALSE,
 CONSTRAINT fk_profile_user FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB;
CREATE TABLE categories (
 category_id INT AUTO_INCREMENT PRIMARY KEY, category_name VARCHAR(100) NOT NULL UNIQUE,
 description TEXT, is_active BOOLEAN NOT NULL DEFAULT TRUE
) ENGINE=InnoDB;
CREATE TABLE services (
 service_id INT AUTO_INCREMENT PRIMARY KEY, provider_id INT NOT NULL, category_id INT NOT NULL,
 service_name VARCHAR(140) NOT NULL, description TEXT, price DECIMAL(10,2) NOT NULL,
 estimated_duration INT NOT NULL DEFAULT 60, is_active BOOLEAN NOT NULL DEFAULT TRUE,
 INDEX ix_services_provider(provider_id), INDEX ix_services_category(category_id),
 CONSTRAINT fk_service_provider FOREIGN KEY(provider_id) REFERENCES provider_profiles(provider_id) ON DELETE RESTRICT,
 CONSTRAINT fk_service_category FOREIGN KEY(category_id) REFERENCES categories(category_id) ON DELETE RESTRICT
) ENGINE=InnoDB;
CREATE TABLE bookings (
 booking_id INT AUTO_INCREMENT PRIMARY KEY, customer_id INT NOT NULL, provider_id INT NOT NULL,
 service_id INT NOT NULL, service_name VARCHAR(140) NOT NULL, booking_date DATE NOT NULL,
 start_time TIME NOT NULL, end_time TIME NOT NULL, address TEXT NOT NULL, problem_description TEXT,
 total_amount DECIMAL(10,2) NOT NULL, status ENUM('pending','accepted','rejected','in_progress','completed','cancelled') NOT NULL DEFAULT 'pending',
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, INDEX ix_booking_customer(customer_id),
 INDEX ix_booking_provider(provider_id), INDEX ix_booking_service(service_id), INDEX ix_booking_status(status),
 INDEX ix_booking_provider_slot(provider_id,booking_date,start_time,end_time),
 CONSTRAINT fk_booking_customer FOREIGN KEY(customer_id) REFERENCES users(user_id) ON DELETE RESTRICT,
 CONSTRAINT fk_booking_provider FOREIGN KEY(provider_id) REFERENCES provider_profiles(provider_id) ON DELETE RESTRICT,
 CONSTRAINT fk_booking_service FOREIGN KEY(service_id) REFERENCES services(service_id) ON DELETE RESTRICT
) ENGINE=InnoDB;
CREATE TABLE provider_availability (
 availability_id INT AUTO_INCREMENT PRIMARY KEY, provider_id INT NOT NULL, day_of_week INT NOT NULL,
 start_time TIME NOT NULL, end_time TIME NOT NULL, is_available BOOLEAN NOT NULL DEFAULT TRUE,
 INDEX ix_avail_provider(provider_id), CONSTRAINT fk_avail_provider FOREIGN KEY(provider_id) REFERENCES provider_profiles(provider_id) ON DELETE CASCADE
) ENGINE=InnoDB;
CREATE TABLE reviews (
 review_id INT AUTO_INCREMENT PRIMARY KEY, booking_id INT NOT NULL UNIQUE, customer_id INT NOT NULL,
 provider_id INT NOT NULL, rating INT NOT NULL, comment TEXT, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 INDEX ix_reviews_customer(customer_id), INDEX ix_reviews_provider(provider_id),
 CONSTRAINT fk_review_booking FOREIGN KEY(booking_id) REFERENCES bookings(booking_id) ON DELETE RESTRICT,
 CONSTRAINT fk_review_customer FOREIGN KEY(customer_id) REFERENCES users(user_id) ON DELETE RESTRICT,
 CONSTRAINT fk_review_provider FOREIGN KEY(provider_id) REFERENCES provider_profiles(provider_id) ON DELETE RESTRICT
) ENGINE=InnoDB;
