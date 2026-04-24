// Package router wires up the HTTP routes for the authentication service.
package router

import (
	"database/sql"
	"net/http"
	"os"

	"backend_login_go/api"
	"backend_login_go/controller"
	"backend_login_go/repository"
	"backend_login_go/service"
	"backend_login_go/utils"
)

// Route pairs an HTTP path with its handler.
type Route struct {
	Path    string
	Handler http.HandlerFunc
}

// RegisterRoutes wires together the dependency graph and returns a configured
// ServeMux. The database connection is opened here using DATABASE_URL from the
// environment so callers do not need to manage it.
func RegisterRoutes() *http.ServeMux {
	db, err := sql.Open("postgres", os.Getenv("DATABASE_URL"))
	if err != nil {
		panic(err)
	}

	userRepository := repository.NewUserRepository(db)
	passwordHasher := utils.NewPasswordHasher()
	errorHandler := controller.NewErrorHandler()

	authService := service.NewAuthService(
		userRepository,
		passwordHasher,
		errorHandler,
	)
	responseHandler := api.NewResponseHandler()

	mux := http.NewServeMux()
	routes := []Route{
		{Path: "/api/login", Handler: api.LoginEndpoint(authService, responseHandler)},
		{Path: "/api/profile", Handler: api.ProfileEndpoint},
	}

	for _, route := range routes {
		mux.HandleFunc(route.Path, route.Handler)
	}

	return mux
}