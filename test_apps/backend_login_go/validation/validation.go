package validation

import (
	"errors"
	"strings"
)

func ValidateUsername(username string) error {
	if username == "" {
		return errors.New("username is required")
	}
	if containsInvalidChars(username) {
		return errors.New("username contains invalid characters")
	}
	return nil
}

func ValidatePassword(password string) error {
	if password == "" {
		return errors.New("password is required")
	}
	if len(password) < 8 {
		return errors.New("password must be at least 8 characters long")
	}
	if containsInvalidChars(password) {
		return errors.New("password contains invalid characters")
	}
	return nil
}

func containsInvalidChars(input string) bool {
	return strings.Contains(input, ";") || strings.Contains(input, "--")
}