package tests

import (
	"testing"
	"backend_login_go/controller"
	"backend_login_go/repository"
	"backend_login_go/utils"
	"backend_login_go/service"
	"database/sql"
	"os"

	_ "github.com/lib/pq"
	"github.com/stretchr/testify/mock"
)

type mockUserRepository struct {
	mock.Mock
}

func (m *mockUserRepository) GetUser(username string) (*controller.User, error) {
	args := m.Called(username)
	return args.Get(0).(*controller.User), args.Error(1)
}

func TestAuthenticate(t *testing.T) {
	db, err := sql.Open("postgres", os.Getenv("DATABASE_URL"))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	userRepository := repository.NewUserRepository(db)
	passwordHasher := utils.NewPasswordHasher()
	errorHandler := controller.NewErrorHandler()
	authController := controller.NewAuthController(userRepository, passwordHasher, errorHandler)
	authService := service.NewAuthService(authController)

	tests := []struct {
		name       string
		creds      controller.Creds
		wantErr    bool
		wantUser   *controller.User
	}{
		{
			name: "valid credentials",
			creds: controller.Creds{
				Username: "admin",
				Password: "password123",
			},
			wantErr: false,
		},
		{
			name: "invalid credentials",
			creds: controller.Creds{
				Username: "admin",
				Password: "wrongpassword",
			},
			wantErr: true,
		},
		{
			name: "empty username",
			creds: controller.Creds{
				Username: "",
				Password: "password123",
			},
			wantErr: true,
		},
		{
			name: "empty password",
			creds: controller.Creds{
				Username: "admin",
				Password: "",
			},
			wantErr: true,
		},
		{
			name: "null user",
			creds: controller.Creds{
				Username: "nonexistent",
				Password: "password123",
			},
			wantErr: true,
		},
		{
			name: "internal server error",
			creds: controller.Creds{
				Username: "admin",
				Password: "password123",
			},
			wantErr: true,
		},
		{
			name: "boundary password length",
			creds: controller.Creds{
				Username: "admin",
				Password: "password1",
			},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			user, err := authService.Authenticate(tt.creds)
			if (err != nil) != tt.wantErr {
				t.Errorf("Authenticate() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if tt.wantUser != nil && user.Username != tt.wantUser.Username {
				t.Errorf("Authenticate() user = %v, want %v", user, tt.wantUser)
			}
		})
	}
}

func TestAuthenticate_MockUserRepository(t *testing.T) {
	mockUserRepository := new(mockUserRepository)
	mockUser := &controller.User{
		ID:       1,
		Username: "admin",
		Status:   "active",
		Password: "password123",
	}
	mockUserRepository.On("GetUser", "admin").Return(mockUser, nil)

	passwordHasher := utils.NewPasswordHasher()
	errorHandler := controller.NewErrorHandler()
	authController := controller.NewAuthController(mockUserRepository, passwordHasher, errorHandler)
	authService := service.NewAuthService(authController)

	creds := controller.Creds{
		Username: "admin",
		Password: "password123",
	}

	user, err := authService.Authenticate(creds)
	if err != nil {
		t.Errorf("Authenticate() error = %v", err)
		return
	}

	if user.Username != "admin" {
		t.Errorf("Authenticate() user = %v, want %v", user, mockUser)
	}
}

func TestAuthenticate_MockUserRepository_InternalServerError(t *testing.T) {
	mockUserRepository := new(mockUserRepository)
	mockUserRepository.On("GetUser", "admin").Return(nil, sql.ErrConnDone)

	passwordHasher := utils.NewPasswordHasher()
	errorHandler := controller.NewErrorHandler()
	authController := controller.NewAuthController(mockUserRepository, passwordHasher, errorHandler)
	authService := service.NewAuthService(authController)

	creds := controller.Creds{
		Username: "admin",
		Password: "password123",
	}

	_, err := authService.Authenticate(creds)
	if err == nil {
		t.Errorf("Authenticate() error = %v, wantErr %v", err, true)
		return
	}
	if err.Error() != "internal server error" {
		t.Errorf("Authenticate() error = %v, want %v", err, "internal server error")
	}
}