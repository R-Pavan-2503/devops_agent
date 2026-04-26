// Package service implements the authentication business logic exposed to the
// HTTP API layer. It depends on repository and interfaces packages only —
// never on controller — to avoid circular imports.
package service

import (
	"backend_login_go/controller"
	"backend_login_go/interfaces"
	"backend_login_go/repository"
)

// Credentials holds the login credentials passed in by the API handler.
type Credentials struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

// User is the sanitised user representation returned to callers of AuthService.
type User struct {
	ID       string
	Username string
	Status   string
	Password string
}

// AuthService orchestrates authentication by delegating to the controller layer.
type AuthService struct {
	userRepository repository.UserRepository
	passwordHasher interfaces.PasswordHasherInterface
	errorHandler   interfaces.ErrorHandlerInterface
}

// NewAuthService creates a new AuthService with the required dependencies.
func NewAuthService(
	userRepository repository.UserRepository,
	passwordHasher interfaces.PasswordHasherInterface,
	errorHandler interfaces.ErrorHandlerInterface,
) *AuthService {
	return &AuthService{
		userRepository: userRepository,
		passwordHasher: passwordHasher,
		errorHandler:   errorHandler,
	}
}

// Authenticate validates the supplied credentials and returns the matching user
// or an error. Delegates business logic to the controller layer.
func (a *AuthService) Authenticate(credentials Credentials) (*User, error) {
	// Convert service-layer credentials to controller-layer credentials
	ctrlCreds := controller.Credentials{
		Username: credentials.Username,
		Password: credentials.Password,
	}

	authController := controller.NewAuthController(a.userRepository, a.passwordHasher, a.errorHandler)
	ctrlUser, err := authController.Authenticate(ctrlCreds)
	if err != nil {
		return nil, err
	}

	return &User{
		ID:       ctrlUser.ID,
		Username: ctrlUser.Username,
		Status:   ctrlUser.Status,
		Password: ctrlUser.Password,
	}, nil
}