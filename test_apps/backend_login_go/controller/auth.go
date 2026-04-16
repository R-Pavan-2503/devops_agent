package controller

import (
	"backend_login_go/errors"
	"backend_login_go/model"
	"backend_login_go/repository"
	"backend_login_go/utils"
	"strings"
)

type Creds struct {
	Username string
	Password string
}

type User struct {
	ID       int
	Username string
	Status   string
	Password string
}

type AuthController interface {
	Authenticate(c Creds) (*User, error)
}

type authControllerImpl struct {
	userRepository repository.UserRepository
	passwordHasher  utils.PasswordHasher
	errorHandler   ErrorHandler
}

func NewAuthController(userRepository repository.UserRepository, passwordHasher utils.PasswordHasher, errorHandler ErrorHandler) AuthController {
	return &authControllerImpl{userRepository: userRepository, passwordHasher: passwordHasher, errorHandler: errorHandler}
}

func (a *authControllerImpl) Authenticate(c Creds) (*User, error) {
	if c.Username == "" || c.Password == "" {
		return nil, a.errorHandler.HandleError("username and password are required", http.StatusBadRequest)
	}

	if len(c.Password) < 8 {
		return nil, a.errorHandler.HandleError("password must be at least 8 characters long", http.StatusBadRequest)
	}

	if strings.Contains(c.Username, ";") || strings.Contains(c.Username, "--") {
		return nil, a.errorHandler.HandleError("username contains invalid characters", http.StatusBadRequest)
	}

	if strings.Contains(c.Password, ";") || strings.Contains(c.Password, "--") {
		return nil, a.errorHandler.HandleError("password contains invalid characters", http.StatusBadRequest)
	}

	user, err := a.userRepository.GetUser(c.Username)
	if err != nil {
		return nil, a.errorHandler.HandleError("internal server error", http.StatusInternalServerError)
	}

	if user == nil {
		return nil, a.errorHandler.HandleError("unauthorized", http.StatusUnauthorized)
	}

	if user.Username == "" || user.Password == "" {
		return nil, a.errorHandler.HandleError("malformed user object", http.StatusInternalServerError)
	}

	err = a.passwordHasher.CompareHashAndPassword(user.Password, c.Password)
	if err != nil {
		return nil, a.errorHandler.HandleError("unauthorized", http.StatusUnauthorized)
	}

	return user, nil
}

type ErrorHandler interface {
	HandleError(message string, code int) error
}

type errorHandlerImpl struct{}

func NewErrorHandler() ErrorHandler {
	return &errorHandlerImpl{}
}

func (e *errorHandlerImpl) HandleError(message string, code int) error {
	return errors.NewError(message, code)
}