// Package utils provides concrete utility implementations used across the stack.
package utils

import (
	"backend_login_go/interfaces"

	"golang.org/x/crypto/bcrypt"
)

type passwordHasher struct{}

// NewPasswordHasher returns a bcrypt-backed password hasher that satisfies
// interfaces.PasswordHasherInterface.
func NewPasswordHasher() interfaces.PasswordHasherInterface {
	return &passwordHasher{}
}

func (p *passwordHasher) CompareHashAndPassword(hashedPassword string, password string) error {
	return bcrypt.CompareHashAndPassword([]byte(hashedPassword), []byte(password))
}

func (p *passwordHasher) HashPassword(password string) (string, error) {
	hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return "", err
	}
	return string(hash), nil
}