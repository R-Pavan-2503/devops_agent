package api

import (
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"net/mail"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"golang.org/x/crypto/bcrypt"
)

// -------------------------------------------------------------------------
// Interfaces & Dependencies (Architecture Fix)
// -------------------------------------------------------------------------

// UserRepo defines the interface for database operations
type UserRepo interface {
	FindByEmail(email string) (*User, error)
}

// TokenService defines the interface for generating tokens
type TokenService interface {
	Generate(userID int, email string) (string, error)
}

// AuthHandler wraps the dependencies for the login logic
type AuthHandler struct {
	Repo         UserRepo
	TokenService TokenService
}

// -------------------------------------------------------------------------
// Domain Models
// -------------------------------------------------------------------------

type User struct {
	ID           int
	Email        string
	PasswordHash string
}

type LoginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type LoginResponse struct {
	Token   string `json:"token"`
	Message string `json:"message"`
}

// -------------------------------------------------------------------------
// Logic & Handlers
// -------------------------------------------------------------------------

func (h *AuthHandler) Login(w http.ResponseWriter, r *http.Request) {
	// Defensive nil checks for dependencies
	if h.Repo == nil {
		h.sendError(w, http.StatusInternalServerError, "Internal server error")
		log.Println("AuthHandler Repo dependency is nil")
		return
	}
	if h.TokenService == nil {
		h.sendError(w, http.StatusInternalServerError, "Internal server error")
		log.Println("AuthHandler TokenService dependency is nil")
		return
	}

	// Ensure request body is closed safely
	if r.Body != nil {
		defer r.Body.Close()
	}

	if r.Method != http.MethodPost {
		h.sendError(w, http.StatusMethodNotAllowed, "Method not allowed")
		return
	}

	// Limit request body size to prevent abuse (1 MB)
	r.Body = http.MaxBytesReader(w, r.Body, 1<<20)

	var req LoginRequest
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&req); err != nil {
		h.sendError(w, http.StatusBadRequest, "Invalid JSON payload")
		return
	}

	// Trim and normalize inputs
	req.Email = strings.TrimSpace(strings.ToLower(req.Email))
	req.Password = strings.TrimSpace(req.Password)

	// Basic validation without revealing which field is missing/invalid
	if req.Email == "" || req.Password == "" {
		h.sendError(w, http.StatusBadRequest, "Email and password must be provided")
		return
	}
	if _, err := mail.ParseAddress(req.Email); err != nil {
		h.sendError(w, http.StatusBadRequest, "Invalid email format")
		return
	}

	// 1. Fetch User
	user, err := h.Repo.FindByEmail(req.Email)
	if err != nil || user == nil {
		// Generic error to avoid user enumeration
		h.sendError(w, http.StatusUnauthorized, "Invalid credentials")
		return
	}
	if user.PasswordHash == "" {
		h.sendError(w, http.StatusUnauthorized, "Invalid credentials")
		return
	}

	// 2. Verify Password using constant‑time compare via bcrypt
	if bcrypt.CompareHashAndPassword([]byte(user.PasswordHash), []byte(req.Password)) != nil {
		h.sendError(w, http.StatusUnauthorized, "Invalid credentials")
		return
	}

	// 3. Generate Token
	token, err := h.TokenService.Generate(user.ID, user.Email)
	if err != nil {
		// Log internal error without leaking details to client
		log.Printf("Token generation failed: %v", err)
		h.sendError(w, http.StatusInternalServerError, "Internal server error")
		return
	}

	// 4. Success Response with security headers
	h.writeJSON(w, http.StatusOK, LoginResponse{
		Token:   token,
		Message: "Login successful",
	})
}

func (h *AuthHandler) sendError(w http.ResponseWriter, code int, msg string) {
	h.writeJSON(w, code, map[string]string{"error": msg})
}

// writeJSON centralises JSON response handling and adds security headers.
func (h *AuthHandler) writeJSON(w http.ResponseWriter, status int, payload interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.Header().Set("Cache-Control", "no-store, must-revalidate")
	w.Header().Set("Pragma", "no-cache")
	w.Header().Set("X-Frame-Options", "DENY")
	w.Header().Set("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(payload); err != nil {
		log.Printf("Failed to write JSON response: %v", err)
	}
}

// -------------------------------------------------------------------------
// Implementations (Security & Quality Fixes)
// -------------------------------------------------------------------------

type JWTService struct {
	secret        []byte
	expirationSec int64
}

// NewJWTService creates a JWTService using environment configuration.
// It validates that the secret is set and meets a minimum length requirement.
func NewJWTService() (*JWTService, error) {
	secret := os.Getenv("JWT_SECRET")
	if secret == "" {
		return nil, errors.New("JWT_SECRET environment variable is not set")
	}
	if len([]byte(secret)) < 32 {
		return nil, errors.New("JWT_SECRET must be at least 32 bytes for sufficient entropy")
	}

	expStr := os.Getenv("JWT_EXP_SECONDS")
	var exp int64 = 86400 // default 24h
	if expStr != "" {
		parsed, err := strconv.ParseInt(expStr, 10, 64)
		if err != nil || parsed <= 0 {
			return nil, fmt.Errorf("invalid JWT_EXP_SECONDS value: %s", expStr)
		}
		exp = parsed
	}
	return &JWTService{
		secret:        []byte(secret),
		expirationSec: exp,
	}, nil
}

// Generate creates a signed JWT containing standard claims and the user's email.
func (s *JWTService) Generate(userID int, email string) (string, error) {
	now := time.Now().UTC()
	claims := jwt.MapClaims{
		"sub":   userID,
		"email": email,
		"iat":   now.Unix(),
		"nbf":   now.Unix(),
		"exp":   now.Add(time.Duration(s.expirationSec) * time.Second).Unix(),
		"aud":   "myapp",
		"iss":   "myapp",
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signed, err := token.SignedString(s.secret)
	if err != nil {
		return "", err
	}
	return signed, nil
}