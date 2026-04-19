package service

import (
	"backend_login_go/controller"
	"backend_login_go/repository"
	"backend_login_go/utils"
)

type AuthService struct {
	authController controller.AuthController
}

func NewAuthService(authController controller.AuthController) *AuthService {
	return &AuthService{authController: authController}
}

func (a *AuthService) Authenticate(c controller.Creds) (*controller.User, error) {
	return a.authController.Authenticate(c)
}