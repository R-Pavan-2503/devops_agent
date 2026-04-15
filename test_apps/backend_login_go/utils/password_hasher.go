package utils

import (
	"golang.org/x/crypto/bcrypt"
)

type PasswordHasher struct{}

func NewPasswordHasher() *PasswordHasher {
	return &PasswordHasher{}
}

func (p *PasswordHasher) HashPassword(password string) (string, error) {
	hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return "", err
	}
	return string(hash), nil
}

func (p *PasswordHasher) CompareHashAndPassword(hashedPassword string, password string) error {
	return bcrypt.CompareHashAndPassword([]byte(hashedPassword), []byte(password))
}