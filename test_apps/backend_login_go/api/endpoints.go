package api

import (
	"encoding/json"
	"net/http"
	"backend_login_go/service"
	"backend_login_go/errors"
	"time"
)

type LoginResponse struct {
	ID        int       `json:"id"`
	Username  string    `json:"username"`
	Status    string    `json:"status"`
	CreatedAt time.Time `json:"created_at"`
	ErrorMessage string `json:"error_message"`
}

type ResponseWriter interface {
	http.ResponseWriter
}

func validateCredentials(username string, password string) error {
	if username == "" || password == "" {
		return errors.NewError("username and password are required", http.StatusBadRequest)
	}
	if len(password) < 8 {
		return errors.NewError("password must be at least 8 characters long", http.StatusBadRequest)
	}
	return nil
}

func decodeRequestBody(r *http.Request) (service.Creds, error) {
	var creds service.Creds
	err := json.NewDecoder(r.Body).Decode(&creds)
	if err != nil {
		return creds, err
	}
	return creds, nil
}

func createLoginResponse(user *service.User) LoginResponse {
	return LoginResponse{
		ID:        user.ID,
		Username:  user.Username,
		Status:    user.Status,
		CreatedAt: time.Now(),
	}
}

func createLoginErrorResponse(err error) LoginResponse {
	return LoginResponse{
		ErrorMessage: err.Error(),
	}
}

func handleLoginResponse(w ResponseWriter, user *service.User) {
	loginResponse := createLoginResponse(user)
	json.NewEncoder(w).Encode(loginResponse)
}

func handleLoginError(w ResponseWriter, err error) {
	loginResponse := createLoginErrorResponse(err)
	json.NewEncoder(w).Encode(loginResponse)
}

type AuthServiceInterface interface {
	Authenticate(creds service.Creds) (*service.User, error)
}

func LoginEndpoint(authService AuthServiceInterface) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		creds, err := decodeRequestBody(r)
		if err != nil {
			http.Error(w, errors.NewError("invalid request body", http.StatusBadRequest).Error(), http.StatusBadRequest)
			return
		}

		err = validateCredentials(creds.Username, creds.Password)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		user, err := authService.Authenticate(creds)
		if err != nil {
			handleLoginError(w, err)
			return
		}

		handleLoginResponse(w, user)
	}
}

func ProfileEndpoint(w http.ResponseWriter, r *http.Request) {
	w.Write([]byte("Profile Placeholder"))
}