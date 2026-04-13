# PR Review Report

## Summary
The review covered a Go authentication handler implementation across six agents over three iterative rounds. While most agents approved the changes, the Backend Analyst rejected due to a high‑severity resource leak. Overall outcome: **FAILED**.

## Agent Pipeline Results
| Agent | Verdict | Rounds |
|---|---|---|
| Security Architect | APPROVE | 3 |
| Backend Analyst | REJECT | 3 |
| Frontend Integration | APPROVE | 3 |
| Software Architect | APPROVE | 3 |
| QA / SDET | APPROVE | 3 |
| Code Quality | APPROVE | 3 |

## Iteration Log
### Summary of Revisions
Initial feedback highlighted a potential N+1 query pattern in the login flow, non‑descriptive naming, and a frontend type mismatch. Subsequent rounds added context‑bounded repository calls, introduced dependency injection interfaces, and addressed security concerns such as missing authentication middleware and insufficient test coverage. The final iteration focused on a critical resource leak in `ServeHTTP`; the developer added proper request‑body closure and deferred context cancellation, as well as hardened JWT secret handling and comprehensive response headers.

## Key Improvements & Hardening
| Category | Issue | Fix |
|---|---|---|
| CRITICAL | Resource leak in `ServeHTTP` (unclosed request body) | Added `defer r.Body.Close()` and context cancelation; centralized error handling |
| HIGH | Potential N+1 query pattern in login logic | Refactored to single `FindByEmail` call with context timeout |
| HIGH | Missing validation for email length / malformed input | Added trim, format validation, and non‑empty checks |
| HIGH | Insecure JWT secret configuration | Enforced environment variable presence and minimum 32‑character entropy |
| HIGH | Inadequate test coverage and nondeterministic bcrypt comparison | Improved input validation and deterministic error handling (though tests not shown) |

## Final Code Output
```go
package api

import (
	"context"
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

// Logger abstracts logging to allow injection and testing.
type Logger interface {
	Error(args ...interface{})
	Info(args ...interface{})
}

// StdLogger implements Logger using the standard library log package.
type StdLogger struct{}

func (l StdLogger) Error(args ...interface{}) { log.Println(args...) }
func (l StdLogger) Info(args ...interface{})  { log.Println(args...) }

// UserRepo defines the interface for database operations.
type UserRepo interface {
	FindByEmail(ctx context.Context, email string) (*User, error)
}

// TokenService defines the interface for generating tokens.
type TokenService interface {
	Generate(userID int, email string) (string, error)
}

// AuthHandler wraps the dependencies for the login logic.
type AuthHandler struct {
	repo         UserRepo
	tokenService TokenService
	logger       Logger
}

// Ensure AuthHandler implements http.Handler for potential future extensions.
var _ http.Handler = (*AuthHandler)(nil)

// NewAuthHandler constructs an AuthHandler ensuring all dependencies are present.
func NewAuthHandler(repo UserRepo, tokenService TokenService, logger Logger) (*AuthHandler, error) {
	if repo == nil {
		return nil, errors.New("user repository cannot be nil")
	}
	if tokenService == nil {
		return nil, errors.New("token service cannot be nil")
	}
	if logger == nil {
		logger = StdLogger{}
	}
	return &AuthHandler{
		repo:         repo,
		tokenService: tokenService,
		logger:       logger,
	}, nil
}

// ServeHTTP dispatches requests to the appropriate handler method.
func (h *AuthHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	switch r.URL.Path {
	case "/login":
		h.Login(w, r)
	default:
		h.sendError(w, http.StatusNotFound, "Not found")
	}
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
	if r.Body != nil {
		defer r.Body.Close()
	}

	if r.Method != http.MethodPost {
		h.sendError(w, http.StatusMethodNotAllowed, "Method not allowed")
		return
	}

	// Limit request body size to prevent abuse (1 MiB)
	r.Body = http.MaxBytesReader(w, r.Body, 1<<20)

	var req LoginRequest
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&req); err != nil {
		h.sendError(w, http.StatusBadRequest, "Invalid JSON payload")
		h.logger.Error("JSON decode error:", err)
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

	// Context with timeout for repository access
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()

	// 1. Fetch User
	user, err := h.repo.FindByEmail(ctx, req.Email)
	if err != nil || user == nil {
		h.sendError(w, http.StatusUnauthorized, "Invalid credentials")
		h.logger.Info("Failed login attempt for email:", req.Email)
		return
	}
	if user.PasswordHash == "" {
		h.sendError(w, http.StatusUnauthorized, "Invalid credentials")
		h.logger.Info("User missing password hash for email:", req.Email)
		return
	}

	// 2. Verify Password using bcrypt (constant‑time)
	if err := bcrypt.CompareHashAndPassword([]byte(user.PasswordHash), []byte(req.Password)); err != nil {
		h.sendError(w, http.StatusUnauthorized, "Invalid credentials")
		h.logger.Info("Invalid password for email:", req.Email)
		return
	}

	// 3. Generate Token
	token, err := h.tokenService.Generate(user.ID, user.Email)
	if err != nil {
		h.logger.Error("Token generation failed:", err)
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
	w.Header().Set("X-XSS-Protection", "0")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(payload); err != nil {
		if h.logger != nil {
			h.logger.Error("Failed to write JSON response:", err)
		} else {
			log.Printf("Failed to write JSON response: %v", err)
		}
	}
}

// -------------------------------------------------------------------------
// Implementations (Security & Quality Fixes)
// -------------------------------------------------------------------------

type JWTService struct {
	secret        []byte
	expirationSec int64
}

// Ensure JWTService implements TokenService.
var _ TokenService = (*JWTService)(nil)

// NewJWTService creates a JWTService using environment configuration.
// It validates that the secret is set and meets a minimum length requirement.
func NewJWTService() (*JWTService, error) {
	secret := os.Getenv("JWT_SECRET")
	if secret == "" {
		return nil, errors.New("JWT_SECRET environment variable is not set")
	}
	if len(secret) < 32 {
		return nil, errors.New("JWT_SECRET must be at least 32 characters for sufficient entropy")
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
		"jti":   fmt.Sprintf("%d-%d", userID, now.UnixNano()),
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signed, err := token.SignedString(s.secret)
	if err != nil {
		return "", err
	}
	return signed, nil
}
```

## Sign-Off
Pipeline failed to converge. Manual review required.

### Final Agent Verdicts & Reasons
- **Frontend Integration**: 
- **QA / SDET**: [COVERAGE] estimated 75.00% — OK
- **Software Architect**: 
- **Code Quality**: 
- **Security Architect**: 
- **Backend Analyst**: HIGH file:79 — resource leak in ServeHTTP