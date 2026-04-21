package api

import (
	"encoding/json"
	"net/http"
	"backend_login_go/service"
	"backend_login_go/validation"
	"time"
	"strings"
)

type LoginResponse struct {
	ID        int    `json:"id"`
	Username  string `json:"username"`
	Status    string `json:"status"`
	CreatedAt string `json:"created_at"`
	ErrorMessage string `json:"error_message"`
	ErrorCode   int      `json:"error_code"`
}

type ResponseWriter interface {
	http.ResponseWriter
}

func decodeRequestBody(r *http.Request) (service.Credentials, error) {
	var credentials service.Credentials
	err := json.NewDecoder(r.Body).Decode(&credentials)
	if err != nil {
		return credentials, validation.NewValidationError("invalid json request")
	}
	if credentials.Username == "" || credentials.Password == "" {
		return credentials, validation.NewValidationError("username and password are required")
	}
	return credentials, nil
}

func validateRequestBody(credentials service.Credentials) error {
	if err := validateUsername(credentials.Username); err != nil {
		return err
	}
	if err := validatePassword(credentials.Password); err != nil {
		return err
	}
	return nil
}

func validateUsername(username string) error {
	if username == "" {
		return validation.NewValidationError("username is required")
	}
	if len(username) < 3 || len(username) > 20 {
		return validation.NewValidationError("username must be between 3 and 20 characters")
	}
	if containsInvalidChars(username) {
		return validation.NewValidationError("username contains invalid characters")
	}
	return nil
}

func validatePassword(password string) error {
	if password == "" {
		return validation.NewValidationError("password is required")
	}
	if len(password) < 8 {
		return validation.NewValidationError("password must be at least 8 characters")
	}
	if containsInvalidChars(password) {
		return validation.NewValidationError("password contains invalid characters")
	}
	return nil
}

func containsInvalidChars(input string) bool {
	return strings.Contains(input, ";") || strings.Contains(input, "--")
}

func createLoginResponse(user *service.User) LoginResponse {
	return LoginResponse{
		ID:        user.ID,
		Username:  user.Username,
		Status:    user.Status,
		CreatedAt: time.Now().Format(time.RFC3339),
	}
}

func createLoginErrorResponse(err error, code int) LoginResponse {
	return LoginResponse{
		ErrorMessage: err.Error(),
		ErrorCode:     code,
	}
}

type ResponseHandler interface {
	HandleResponse(w ResponseWriter, user *service.User)
	HandleError(w ResponseWriter, err error, code int)
}

type responseHandlerImpl struct{}

func NewResponseHandler() ResponseHandler {
	return &responseHandlerImpl{}
}

func (r *responseHandlerImpl) HandleResponse(w ResponseWriter, user *service.User) {
	loginResponse := createLoginResponse(user)
	json.NewEncoder(w).Encode(loginResponse)
}

func (r *responseHandlerImpl) HandleError(w ResponseWriter, err error, code int) {
	loginResponse := createLoginErrorResponse(err, code)
	json.NewEncoder(w).Encode(loginResponse)
}

type AuthServiceInterface interface {
	Authenticate(credentials service.Credentials) (*service.User, error)
}

func LoginEndpoint(authService AuthServiceInterface, responseHandler ResponseHandler) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" {
			http.Error(w, "invalid request method", http.StatusBadRequest)
			return
		}

		credentials, err := decodeRequestBody(r)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		if err := validateRequestBody(credentials); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		user, err := authService.Authenticate(credentials)
		if err != nil {
			responseHandler.HandleError(w, err, http.StatusUnauthorized)
			return
		}

		responseHandler.HandleResponse(w, user)
	}
}

func ProfileEndpoint(w http.ResponseWriter, r *http.Request) {
	w.Write([]byte("Profile Placeholder"))
}