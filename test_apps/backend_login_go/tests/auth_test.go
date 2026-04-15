package tests

import (
	"testing"
	"backend_login_go/controller"
	"backend_login_go/repository"
	"backend_login_go/utils"
	"database/sql"
	"os"

	_ "github.com/lib/pq"
)

func TestAuthenticate(t *testing.T) {
	// Connect to the database
	db, err := sql.Open("postgres", os.Getenv("DATABASE_URL"))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	// Create a new user repository
	userRepository := repository.NewUserRepository(db)

	// Create a new password hasher
	passwordHasher := utils.NewPasswordHasher()

	// Create a new auth controller
	authController := controller.NewAuthController(userRepository, passwordHasher)

	// Test with valid credentials
	creds := controller.Creds{Username: "admin", Password: "password123"}
	user, err := authController.Authenticate(creds)
	if err != nil {
		t.Fatalf("expected no error")
	}
	if user.Username != "admin" {
		t.Fatalf("expected admin")
	}

	// Test with invalid credentials
	creds = controller.Creds{Username: "admin", Password: "wrongpassword"}
	_, err = authController.Authenticate(creds)
	if err == nil {
		t.Fatalf("expected error")
	}

	// Test with empty username
	creds = controller.Creds{Username: "", Password: "password123"}
	_, err = authController.Authenticate(creds)
	if err == nil {
		t.Fatalf("expected error")
	}

	// Test with empty password
	creds = controller.Creds{Username: "admin", Password: ""}
	_, err = authController.Authenticate(creds)
	if err == nil {
		t.Fatalf("expected error")
	}
}