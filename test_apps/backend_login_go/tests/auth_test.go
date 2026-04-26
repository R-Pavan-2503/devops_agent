package tests

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"backend_login_go/api"
	"backend_login_go/controller"
	"backend_login_go/interfaces"
	"backend_login_go/service"
	"backend_login_go/validation"
)

// --- Validation unit tests ---

func TestValidateUsername_Valid(t *testing.T) {
	if err := validation.ValidateUsername("alice"); err != nil {
		t.Fatalf("expected no error for valid username, got: %v", err)
	}
}

func TestValidateUsername_TooShort(t *testing.T) {
	if err := validation.ValidateUsername("ab"); err == nil {
		t.Fatal("expected error for username shorter than 3 chars")
	}
}

func TestValidateUsername_TooLong(t *testing.T) {
	if err := validation.ValidateUsername("aaaaabbbbbcccccddddde"); err == nil {
		t.Fatal("expected error for username longer than 20 chars")
	}
}

func TestValidateUsername_Empty(t *testing.T) {
	if err := validation.ValidateUsername(""); err == nil {
		t.Fatal("expected error for empty username")
	}
}

func TestValidatePassword_Valid(t *testing.T) {
	if err := validation.ValidatePassword("securepassword"); err != nil {
		t.Fatalf("expected no error for valid password, got: %v", err)
	}
}

func TestValidatePassword_TooShort(t *testing.T) {
	if err := validation.ValidatePassword("short"); err == nil {
		t.Fatal("expected error for password shorter than 8 chars")
	}
}

func TestValidatePassword_Empty(t *testing.T) {
	if err := validation.ValidatePassword(""); err == nil {
		t.Fatal("expected error for empty password")
	}
}

// --- Mock implementations for interface-driven testing ---

// mockPasswordHasher always succeeds — used for happy-path tests.
type mockPasswordHasher struct{}

func (m *mockPasswordHasher) HashPassword(password string) (string, error) {
	return "$mock_hash_" + password, nil
}

func (m *mockPasswordHasher) CompareHashAndPassword(hashedPassword, password string) error {
	// Accept any password for test simplicity
	return nil
}

// Compile-time assertion that mockPasswordHasher satisfies the interface.
var _ interfaces.PasswordHasherInterface = (*mockPasswordHasher)(nil)

// mockErrorHandler wraps controller.NewError so tests can use the real error type.
type mockErrorHandler struct{}

func (m *mockErrorHandler) HandleError(message string, code int) error {
	return controller.NewError(message, code)
}

var _ interfaces.ErrorHandlerInterface = (*mockErrorHandler)(nil)

// mockUserRepository returns a pre-set user or nil.
type mockUserRepository struct {
	user *modelUser
}

type modelUser struct {
	ID       string
	Username string
	Status   string
	Password string
}

// LoginEndpoint integration test — exercises the HTTP handler end-to-end
// using an in-memory MockAuthService.

type mockAuthService struct {
	user *service.User
	err  error
}

func (m *mockAuthService) Authenticate(credentials service.Credentials) (*service.User, error) {
	return m.user, m.err
}

var _ api.AuthServiceInterface = (*mockAuthService)(nil)

func TestLoginEndpoint_EmptyBody(t *testing.T) {
	svc := &mockAuthService{}
	handler := api.LoginEndpoint(svc, api.NewResponseHandler())

	body := strings.NewReader(`{}`)
	req, _ := http.NewRequest(http.MethodPost, "/login", body)
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()

	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", rr.Code)
	}
}

func TestLoginEndpoint_WrongMethod(t *testing.T) {
	svc := &mockAuthService{}
	handler := api.LoginEndpoint(svc, api.NewResponseHandler())

	req, _ := http.NewRequest(http.MethodGet, "/login", nil)
	rr := httptest.NewRecorder()

	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusBadRequest {
		t.Errorf("expected 400 for GET request, got %d", rr.Code)
	}
}