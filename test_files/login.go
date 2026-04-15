package main

import (
	"encoding/json"
	"log"
	"net/http"
	"time"
)

// Mock database for demonstration.
// IN PRODUCTION: Use a real database and NEVER store plain-text passwords. Use bcrypt.
var mockDB = map[string]string{
	"admin": "password123",
	"user":  "letmein88",
}

// Credentials struct maps to the incoming JSON request body
type Credentials struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

// APIResponse struct standardizes our JSON replies
type APIResponse struct {
	Success bool   `json:"success"`
	Message string `json:"message"`
}

// Login API Endpoint (POST only)
func LoginAPI(w http.ResponseWriter, r *http.Request) {
	// Set the content type to JSON
	w.Header().Set("Content-Type", "application/json")

	// Only accept POST requests
	if r.Method != http.MethodPost {
		w.WriteHeader(http.StatusMethodNotAllowed)
		json.NewEncoder(w).Encode(APIResponse{Success: false, Message: "Method not allowed"})
		return
	}

	// 1. Parse the JSON body
	var creds Credentials
	err := json.NewDecoder(r.Body).Decode(&creds)
	if err != nil {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(APIResponse{Success: false, Message: "Invalid request payload"})
		return
	}

	// 2. Authenticate
	expectedPassword, userExists := mockDB[creds.Username]
	if !userExists || expectedPassword != creds.Password {
		w.WriteHeader(http.StatusUnauthorized)
		json.NewEncoder(w).Encode(APIResponse{Success: false, Message: "Invalid username or password"})
		return
	}

	// 3. Success: Set an HttpOnly cookie for session management
	// In production, the value should be a secure, random session ID or a JWT.
	expirationTime := time.Now().Add(24 * time.Hour)
	http.SetCookie(w, &http.Cookie{
		Name:     "session_token",
		Value:    creds.Username, // Replace with actual token in prod
		Expires:  expirationTime,
		Path:     "/",
		HttpOnly: true, // Crucial: Prevents XSS attacks from reading the cookie
		// Secure: true, // Uncomment in production to ensure cookie is only sent over HTTPS
		SameSite: http.SameSiteStrictMode, // Protects against CSRF attacks
	})

	// 4. Return success response
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(APIResponse{Success: true, Message: "Login successful"})
}

// Protected API Endpoint (Requires valid cookie)
func ProfileAPI(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")

	// 1. Check for the session cookie
	cookie, err := r.Cookie("session_token")
	if err != nil {
		if err == http.ErrNoCookie {
			w.WriteHeader(http.StatusUnauthorized)
			json.NewEncoder(w).Encode(APIResponse{Success: false, Message: "Unauthorized: No session found"})
			return
		}
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(APIResponse{Success: false, Message: "Bad request"})
		return
	}

	// 2. If cookie exists, user is authenticated
	// In production, validate this token against your database or verify the JWT signature here.
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(APIResponse{
		Success: true,
		Message: "Welcome to your profile, " + cookie.Value,
	})
}

// Logout API Endpoint
func LogoutAPI(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")

	// Clear the cookie by setting its expiration date to the past
	http.SetCookie(w, &http.Cookie{
		Name:     "session_token",
		Value:    "",
		Expires:  time.Now().Add(-1 * time.Hour),
		Path:     "/",
		HttpOnly: true,
	})

	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(APIResponse{Success: true, Message: "Logged out successfully"})
}

func main() {
	// Register API routes
	http.HandleFunc("/api/login", LoginAPI)
	http.HandleFunc("/api/profile", ProfileAPI)
	http.HandleFunc("/api/logout", LogoutAPI)

	log.Println("Backend API running on http://localhost:8080")
	log.Fatal(http.ListenAndServe(":8080", nil))
}
