// Package login provides HTTP handler for user authentication.
// It follows clean architecture principles: the handler layer only
// deals with HTTP concerns; database access is hidden behind a
// UserRepository interface for full testability.
package login

import (
	"database/sql"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"time"

	"golang.org/x/crypto/bcrypt"
)

// ─── Domain types ────────────────────────────────────────────────────────────

// loginRequest is decoded from the JSON request body.
type loginRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

// successResponse is returned on a successful authentication.
type successResponse struct {
	Data struct {
		ID        int       `json:"id"`
		Status    string    `json:"status"`
		CreatedAt time.Time `json:"created_at"`
	} `json:"data"`
}

// errorResponse is returned on any failure.
type errorResponse struct {
	Error struct {
		Code         int    `json:"code"`
		ErrorMessage string `json:"error_message"`
	} `json:"error"`
}

// ─── Repository interface (enables full unit-test mocking) ───────────────────

// UserRepository abstracts all database access needed by LoginHandler.
// Tests inject a fake implementation; production code uses sqlUserRepository.
type UserRepository interface {
	// FindByUsername returns (id, passwordHash, nil) when the user exists,
	// or (0, "", sql.ErrNoRows) when not found, or another error on DB failure.
	FindByUsername(username string) (id int, passwordHash string, err error)
}

// ─── Production repository (depends on *sql.DB, injected at startup) ─────────

// sqlUserRepository is the real MySQL-backed implementation.
type sqlUserRepository struct {
	db *sql.DB
}

// NewSQLUserRepository constructs a production UserRepository.
// The caller owns the *sql.DB connection pool and must close it.
func NewSQLUserRepository(db *sql.DB) UserRepository {
	return &sqlUserRepository{db: db}
}

// FindByUsername executes a single parameterized query to prevent SQL injection.
func (r *sqlUserRepository) FindByUsername(username string) (int, string, error) {
	var id int
	var hash string
	err := r.db.QueryRow(
		"SELECT id, password_hash FROM users WHERE username = ?", username,
	).Scan(&id, &hash)
	return id, hash, err
}

// ─── HTTP Handler (pure function, no global state) ───────────────────────────

// LoginHandler handles POST /login.
// It is a plain struct so the repository can be injected via the constructor,
// keeping this handler fully unit-testable without any real database.
type LoginHandler struct {
	repo UserRepository
}

// NewLoginHandler creates a LoginHandler with the given repository.
func NewLoginHandler(repo UserRepository) *LoginHandler {
	return &LoginHandler{repo: repo}
}

// ServeHTTP implements http.Handler.
func (h *LoginHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// ── Enforce POST ─────────────────────────────────────────────────────────
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	// ── Decode & validate request body ───────────────────────────────────────
	var req loginRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if req.Username == "" || req.Password == "" {
		writeError(w, http.StatusUnprocessableEntity, "username and password are required")
		return
	}

	// ── Look up user ─────────────────────────────────────────────────────────
	id, storedHash, err := h.repo.FindByUsername(req.Username)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			// Return 401 (not 404) to avoid username enumeration
			writeError(w, http.StatusUnauthorized, "invalid username or password")
			return
		}
		log.Printf("[LoginHandler] db error: %v", err)
		writeError(w, http.StatusInternalServerError, "internal server error")
		return
	}

	// ── Verify password (constant-time bcrypt comparison) ────────────────────
	if err := bcrypt.CompareHashAndPassword([]byte(storedHash), []byte(req.Password)); err != nil {
		writeError(w, http.StatusUnauthorized, "invalid username or password")
		return
	}

	// ── Return success payload ────────────────────────────────────────────────
	var resp successResponse
	resp.Data.ID = id
	resp.Data.Status = "success"
	resp.Data.CreatedAt = time.Now().UTC()

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		log.Printf("[LoginHandler] response encoding error: %v", err)
	}
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

// writeError serialises a consistent JSON error envelope and sets the status code.
func writeError(w http.ResponseWriter, code int, message string) {
	var resp errorResponse
	resp.Error.Code = code
	resp.Error.ErrorMessage = message

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		log.Printf("[LoginHandler] error encoding error response: %v", err)
	}
}
