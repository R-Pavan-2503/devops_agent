package api

import (
	"bytes"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
)

// --- Mocks ---

type mockUserRepo struct {
	user *User
	err  error
}

func (m *mockUserRepo) FindByEmail(email string) (*User, error) {
	return m.user, m.err
}

type mockTokenService struct {
	token string
	err   error
}

func (m *mockTokenService) Generate(userID int, email string) (string, error) {
	return m.token, m.err
}

// --- Tests ---

func TestLoginHandler(t *testing.T) {
	// A valid hashed password for "password123"
	validHash := "$2a$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy"

	tests := []struct {
		name           string
		method         string
		payload        interface{}
		mockUser       *User
		mockUserErr    error
		mockTokenErr   error
		expectedStatus int
	}{
		{
			name:   "Success - Valid Credentials",
			method: http.MethodPost,
			payload: LoginRequest{
				Email:    "test@example.com",
				Password: "password123",
			},
			mockUser:       &User{ID: 1, Email: "test@example.com", PasswordHash: validHash},
			expectedStatus: http.StatusOK,
		},
		{
			name:   "Failure - Wrong Password",
			method: http.MethodPost,
			payload: LoginRequest{
				Email:    "test@example.com",
				Password: "wrongpassword",
			},
			mockUser:       &User{ID: 1, Email: "test@example.com", PasswordHash: validHash},
			expectedStatus: http.StatusUnauthorized,
		},
		{
			name:   "Failure - User Not Found",
			method: http.MethodPost,
			payload: LoginRequest{
				Email:    "nonexistent@example.com",
				Password: "password123",
			},
			mockUser:       nil,
			mockUserErr:    errors.New("user not found"),
			expectedStatus: http.StatusUnauthorized,
		},
		{
			name:           "Failure - Invalid Method (GET)",
			method:         http.MethodGet,
			payload:        nil,
			expectedStatus: http.StatusMethodNotAllowed,
		},
		{
			name:           "Failure - Malformed JSON",
			method:         http.MethodPost,
			payload:        "not-a-json-object",
			expectedStatus: http.StatusBadRequest,
		},
		{
			name:   "Failure - Missing Fields",
			method: http.MethodPost,
			payload: LoginRequest{
				Email: "", // Missing both implies missing fields
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name:   "Failure - Invalid Email Format",
			method: http.MethodPost,
			payload: LoginRequest{
				Email:    "notanemail",
				Password: "password123",
			},
			expectedStatus: http.StatusBadRequest,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Setup mock dependencies
			handler := &AuthHandler{
				Repo:         &mockUserRepo{user: tt.mockUser, err: tt.mockUserErr},
				TokenService: &mockTokenService{token: "mock.jwt.token", err: tt.mockTokenErr},
			}

			// Prepare request body
			var body []byte
			if tt.payload != nil {
				if s, ok := tt.payload.(string); ok {
					body = []byte(s) // handling malformed json explicitly
				} else {
					body, _ = json.Marshal(tt.payload)
				}
			}

			// Create a request and a response recorder
			req := httptest.NewRequest(tt.method, "/login", bytes.NewBuffer(body))
			rr := httptest.NewRecorder()

			// Execute the handler
			handler.Login(rr, req)

			// Assertions
			if rr.Code != tt.expectedStatus {
				t.Errorf("%s: expected status %d, got %d", tt.name, tt.expectedStatus, rr.Code)
			}

			// For success case, verify we actually got a token
			if tt.expectedStatus == http.StatusOK {
				var resp LoginResponse
				if err := json.NewDecoder(rr.Body).Decode(&resp); err != nil {
					t.Fatalf("Failed to decode success response: %v", err)
				}
				if resp.Token == "" {
					t.Error("Expected token in response, got empty string")
				}
			}
		})
	}
}