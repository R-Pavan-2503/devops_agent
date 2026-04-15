package controller

import (
	"backend_login_go/errors"
	"backend_login_go/model"
	"backend_login_go/repository"
	"backend_login_go/utils"
)

type Creds struct {
	Username string
	Password string
}

type User struct {
	ID       int
	Username string
	Status   string
}

type AuthController struct {
	userRepository repository.UserRepository
	passwordHasher  utils.PasswordHasher
}

func NewAuthController(userRepository repository.UserRepository, passwordHasher utils.PasswordHasher) *AuthController {
	return &AuthController{userRepository: userRepository, passwordHasher: passwordHasher}
}

func (a *AuthController) Authenticate(c Creds) (*User, error) {
	if c.Username == "" || c.Password == "" {
		return nil, errors.NewError("username and password are required", http.StatusBadRequest)
	}

	user, err := a.userRepository.GetUser(c.Username)
	if err != nil {
		return nil, errors.NewError("internal server error", http.StatusInternalServerError)
	}

	if user == nil {
		return nil, errors.NewError("unauthorized", http.StatusUnauthorized)
	}

	err = a.passwordHasher.CompareHashAndPassword(user.Password, c.Password)
	if err != nil {
		return nil, errors.NewError("unauthorized", http.StatusUnauthorized)
	}

	return user, nil
}