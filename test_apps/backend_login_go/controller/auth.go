package controller

import (
	"backend_login_go/interfaces"
	"backend_login_go/model"
	"backend_login_go/repository"
	"backend_login_go/validation"
	"net/http"
)

// Credentials holds the login credentials from the HTTP request body.
type Credentials struct {
	Username string
	Password string
}

// User is the sanitised view of a model.User returned to the API layer.
type User struct {
	ID       string
	Username string
	Status   string
	Password string
}

// AuthController is the public interface for the auth business logic.
type AuthController interface {
	Authenticate(credentials Credentials) (*User, error)
}

// UserRepositoryInterface abstracts the data-access layer so the controller
// can be tested without a real database connection.
type UserRepositoryInterface interface {
	GetUser(username string) (*model.User, error)
}

type authControllerImpl struct {
	userRepository repository.UserRepository
	passwordHasher interfaces.PasswordHasherInterface
	errorHandler   interfaces.ErrorHandlerInterface
}

// NewAuthController wires together the controller with its dependencies.
func NewAuthController(
	userRepository repository.UserRepository,
	passwordHasher interfaces.PasswordHasherInterface,
	errorHandler interfaces.ErrorHandlerInterface,
) AuthController {
	return &authControllerImpl{
		userRepository: userRepository,
		passwordHasher: passwordHasher,
		errorHandler:   errorHandler,
	}
}

// Authenticate validates credentials and returns the authenticated user or an error.
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

	user, err := a.userRepository.GetUser(credentials.Username)
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

// errorHandlerImpl is the production implementation of ErrorHandlerInterface.
type errorHandlerImpl struct{}

// NewErrorHandler creates a production-ready error handler.
func NewErrorHandler() interfaces.ErrorHandlerInterface {
	return &errorHandlerImpl{}
}

func (e *errorHandlerImpl) HandleError(message string, code int) error {
	return NewError(message, code)
}