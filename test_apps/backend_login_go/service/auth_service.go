package service

import (
	"backend_login_go/controller"
	"backend_login_go/repository"
	"backend_login_go/utils"
)

type AuthService struct {
	userRepository repository.UserRepository
	passwordHasher  utils.PasswordHasherInterface
	errorHandler  controller.ErrorHandlerInterface
}

func NewAuthService(userRepository repository.UserRepository, passwordHasher utils.PasswordHasherInterface, errorHandler controller.ErrorHandlerInterface) *AuthService {
	return &AuthService{userRepository: userRepository, passwordHasher: passwordHasher, errorHandler: errorHandler}
}

func (a *AuthService) Authenticate(credentials controller.Credentials) (*controller.User, error) {
	authController := controller.NewAuthController(a.userRepository, a.passwordHasher, a.errorHandler)
	return authController.Authenticate(credentials)
}