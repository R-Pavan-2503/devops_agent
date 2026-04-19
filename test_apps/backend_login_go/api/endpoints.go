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
	ID        int       `json:"id"`
	Username  string    `json:"username"`
	Status    string    `json:"status"`
	CreatedAt time.Time `json:"created_at"`
	ErrorMessage string `json:"error_message"`
}

type ResponseWriter interface {
	http.ResponseWriter
}

func decodeRequestBody(r *http.Request) (service.Creds, error) {
	var creds service.Creds
	err := json.NewDecoder(r.Body).Decode(&creds)
	if err != nil {
		return creds, err
	}
	if creds.Username == "" || creds.Password == "" {
		return creds, errors.New("username and password are required")
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

type ResponseHandler interface {
	HandleResponse(w ResponseWriter, user *service.User)
	HandleError(w ResponseWriter, err error)
}

type responseHandlerImpl struct{}

func NewResponseHandler() ResponseHandler {
	return &responseHandlerImpl{}
}

func (r *responseHandlerImpl) HandleResponse(w ResponseWriter, user *service.User) {
	loginResponse := createLoginResponse(user)
	json.NewEncoder(w).Encode(loginResponse)
}

func (r *responseHandlerImpl) HandleError(w ResponseWriter, err error) {
	loginResponse := createLoginErrorResponse(err)
	json.NewEncoder(w).Encode(loginResponse)
}

type AuthServiceInterface interface {
	Authenticate(creds service.Creds) (*service.User, error)
}

func LoginEndpoint(authService AuthServiceInterface, responseHandler ResponseHandler) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		creds, err := decodeRequestBody(r)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		if err := validation.ValidateUsername(creds.Username); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		if err := validation.ValidatePassword(creds.Password); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		user, err := authService.Authenticate(creds)
		if err != nil {
			responseHandler.HandleError(w, err)
			return
		}

		responseHandler.HandleResponse(w, user)
	}
}

func ProfileEndpoint(w http.ResponseWriter, r *http.Request) {
	w.Write([]byte("Profile Placeholder"))
}