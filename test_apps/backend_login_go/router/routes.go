package router

import (
	"net/http"
	"backend_login_go/api"
	"backend_login_go/service"
)

type Route struct {
	Path    string
	Handler http.HandlerFunc
}

func RegisterRoutes(authService service.AuthService) *http.ServeMux {
	mux := http.NewServeMux()
	db, err := sql.Open("postgres", os.Getenv("DATABASE_URL"))
	if err != nil {
		panic(err)
	}
	userRepository := repository.NewUserRepository(db, logger.NewLogger())
	passwordHasher := utils.NewPasswordHasher()
	logger := logger.NewLogger()
	authController := controller.NewAuthController(userRepository, passwordHasher, logger)
	routes := []Route{
		{Path: "/api/login", Handler: api.LoginEndpoint(authService, api.NewResponseHandler())},
		{Path: "/api/profile", Handler: api.ProfileEndpoint},
	}

	for _, route := range routes {
		mux.HandleFunc(route.Path, route.Handler)
	}

	return mux
}