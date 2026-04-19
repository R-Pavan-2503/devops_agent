package controller

import (
	"backend_login_go/errors"
	"backend_login_go/model"
	"backend_login_go/repository"
	"backend_login_go/utils"
	"backend_login_go/validation"
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

type UserRepositoryInterface interface {
	GetUser(username string) (*model.User, error)
}

type PasswordHasherInterface interface {
	CompareHashAndPassword(hashedPassword string, password string) error
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

func (a *authControllerImpl) Authenticate(c Creds) (*User, error) {
	if err := validation.ValidateUsername(c.Username); err != nil {
		return nil, a.errorHandler.HandleError(err.Error(), http.StatusBadRequest)
	}
	if err := validation.ValidatePassword(c.Password); err != nil {
		return nil, a.errorHandler.HandleError(err.Error(), http.StatusBadRequest)
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

	return &User{
		ID:       user.ID,
		Username: user.Username,
		Status:   user.Status,
		Password: user.Password,
	}, nil
}

type errorHandlerImpl struct{}

func NewErrorHandler() ErrorHandlerInterface {
	return &errorHandlerImpl{}
}

func (e *errorHandlerImpl) HandleError(message string, code int) error {
	return errors.NewError(message, code)
}