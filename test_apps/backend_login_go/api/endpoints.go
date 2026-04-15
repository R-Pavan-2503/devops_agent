package api

import (
	"encoding/json"
	"net/http"
	"backend_login_go/controller"
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

func LoginEndpoint(w http.ResponseWriter, r *http.Request) {
	var creds controller.Creds
	
	err := json.NewDecoder(r.Body).Decode(&creds)
	if err != nil {
		http.Error(w, errors.NewError("invalid request body", http.StatusBadRequest).Error(), http.StatusBadRequest)
		return
	}
	
	if creds.Username == "" || creds.Password == "" {
		http.Error(w, errors.NewError("username and password are required", http.StatusBadRequest).Error(), http.StatusBadRequest)
		return
	}
	
	user, err := controller.Authenticate(creds)
	if err != nil {
		loginResponse := LoginResponse{
			ErrorMessage: err.Error(),
		}
		json.NewEncoder(w).Encode(loginResponse)
		return
	}
	
	loginResponse := LoginResponse{
		ID:        user.ID,
		Username:  user.Username,
		Status:    user.Status,
		CreatedAt: time.Now(),
	}
	
	json.NewEncoder(w).Encode(loginResponse)
}

func ProfileEndpoint(w http.ResponseWriter, r *http.Request) {
	w.Write([]byte("Profile Placeholder"))
}