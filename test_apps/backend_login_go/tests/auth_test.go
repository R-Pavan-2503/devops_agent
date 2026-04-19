package tests

import (
	"backend_login_go/controller"
	"backend_login_go/repository"
	"backend_login_go/utils"
	"backend_login_go/validation"
	"testing"
	"database/sql"
	"net/http"
)

func TestAuthControllerImpl_Authenticate(t *testing.T) {
	// Create a test user repository
	db, err := sql.Open("postgres", "user:password@localhost/database")
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	userRepository := repository.NewUserRepository(db)

	// Create a test password hasher
	passwordHasher := utils.NewPasswordHasher()

	// Create a test error handler
	errorHandler := controller.NewErrorHandler()

	// Create a test auth controller
	authController := controller.NewAuthController(userRepository, passwordHasher, errorHandler)

	// Test the Authenticate function
	credentials := controller.Credentials{
		Username: "testuser",
		Password: "testpassword",
	}

	user, err := authController.Authenticate(credentials)
	if err != nil {
		t.Fatal(err)
	}

	if user.Username != "testuser" {
		t.Errorf("expected username to be 'testuser', but got '%s'", user.Username)
	}

	// Test null input handling
	credentials = controller.Credentials{
		Username: "",
		Password: "",
	}

	_, err = authController.Authenticate(credentials)
	if err == nil {
		t.Errorf("expected error for null input, but got nil")
	}

	// Test empty input handling
	credentials = controller.Credentials{
		Username: "   ",
		Password: "   ",
	}

	_, err = authController.Authenticate(credentials)
	if err == nil {
		t.Errorf("expected error for empty input, but got nil")
	}

	// Test boundary input handling
	credentials = controller.Credentials{
		Username: strings.Repeat("a", 21),
		Password: strings.Repeat("a", 9),
	}

	_, err = authController.Authenticate(credentials)
	if err == nil {
		t.Errorf("expected error for boundary input, but got nil")
	}
}

func TestAuthService_Authenticate(t *testing.T) {
	// Create a test user repository
	db, err := sql.Open("postgres", "user:password@localhost/database")
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	userRepository := repository.NewUserRepository(db)

	// Create a test password hasher
	passwordHasher := utils.NewPasswordHasher()

	// Create a test error handler
	errorHandler := controller.NewErrorHandler()

	// Create a test auth service
	authService := service.NewAuthService(userRepository, passwordHasher, errorHandler)

	// Test the Authenticate function
	credentials := controller.Credentials{
		Username: "testuser",
		Password: "testpassword",
	}

	user, err := authService.Authenticate(credentials)
	if err != nil {
		t.Fatal(err)
	}

	if user.Username != "testuser" {
		t.Errorf("expected username to be 'testuser', but got '%s'", user.Username)
	}
}

func TestLoginEndpoint(t *testing.T) {
	// Create a test user repository
	db, err := sql.Open("postgres", "user:password@localhost/database")
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	userRepository := repository.NewUserRepository(db)

	// Create a test password hasher
	passwordHasher := utils.NewPasswordHasher()

	// Create a test error handler
	errorHandler := controller.NewErrorHandler()

	// Create a test auth service
	authService := service.NewAuthService(userRepository, passwordHasher, errorHandler)

	// Create a test response handler
	responseHandler := api.NewResponseHandler()

	// Create a test login endpoint
	loginEndpoint := api.LoginEndpoint(authService, responseHandler)

	// Test the login endpoint
	req, err := http.NewRequest("POST", "/api/login", strings.NewReader(`{"username": "testuser", "password": "testpassword"}`))
	if err != nil {
		t.Fatal(err)
	}

	w := &http.ResponseRecorder{}
	loginEndpoint(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status code to be %d, but got %d", http.StatusOK, w.Code)
	}
}

type ResponseRecorder struct {
	Code int
}

func (r *ResponseRecorder) WriteHeader(code int) {
	r.Code = code
}

func (r *ResponseRecorder) Write(b []byte) (int, error) {
	return len(b), nil
}

func (r *ResponseRecorder) Header() http.Header {
	return http.Header{}
}