package controller

import (
	"backend_login_go/errors"
	"backend_login_go/model"
	"backend_login_go/repository"
	"backend_login_go/utils"
	"strings"
)

type Credentials struct {
	Username string
	Password string
}

type User struct {
	ID       string
	Username string
	Status   string
	Password string
}

type AuthController interface {
	Authenticate(credentials Credentials) (*User, error)
}

type UserRepositoryInterface interface {
	GetUser(username string) (*model.User, error)
}

type PasswordHasherInterface interface {
	CompareHashAndPassword(hashedPassword string, password string) error
	HashPassword(password string) (string, error)
}

type ErrorHandlerInterface interface {
	HandleError(message string, code int) error
}

type authControllerImpl struct {
	userRepository UserRepositoryInterface
	passwordHasher  PasswordHasherInterface
	errorHandler   ErrorHandlerInterface
}

func NewAuthController(userRepository UserRepositoryInterface, passwordHasher PasswordHasherInterface, errorHandler ErrorHandlerInterface) AuthController {
	return &authControllerImpl{userRepository: userRepository, passwordHasher: passwordHasher, errorHandler: errorHandler}
}

func (a *authControllerImpl) Authenticate(credentials Credentials) (*User, error) {
	if credentials.Username == "" || credentials.Password == "" {
		return nil, a.errorHandler.HandleError("username and password are required", http.StatusBadRequest)
	}
	if err := validation.ValidateUsername(credentials.Username); err != nil {
		return nil, a.errorHandler.HandleError(err.Error(), http.StatusBadRequest)
	}
	if err := validation.ValidatePassword(credentials.Password); err != nil {
		return nil, a.errorHandler.HandleError(err.Error(), http.StatusBadRequest)
	}

	user, err := a.getUser(credentials.Username)
	if err != nil {
		return nil, a.errorHandler.HandleError("internal server error", http.StatusInternalServerError)
	}

	if user == nil {
		return nil, a.errorHandler.HandleError("unauthorized", http.StatusUnauthorized)
	}

	if err := a.passwordHasher.CompareHashAndPassword(user.Password, credentials.Password); err != nil {
		return nil, a.errorHandler.HandleError("unauthorized", http.StatusUnauthorized)
	}

	return &User{
		ID:       user.ID,
		Username: user.Username,
		Status:   user.Status,
		Password: user.Password,
	}, nil
}

func (a *authControllerImpl) getUser(username string) (*model.User, error) {
	return a.userRepository.GetUser(username)
}

type errorHandlerImpl struct{}

func NewErrorHandler() ErrorHandlerInterface {
	return &errorHandlerImpl{}
}

func (e *errorHandlerImpl) HandleError(message string, code int) error {
	return errors.NewError(message, code)
}